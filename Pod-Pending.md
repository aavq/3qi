## Краткое резюме

Pod остаётся в `Pending`, потому что **ни один из 28 узлов не прошёл все фильтры планировщика**:

* три разных taint’а (`dedicated-node: clickhouse`, `node-role.kubernetes.io/control-plane`, `marketdata-test: true`) —и под у вас не содержит соответствующих toleration’ов;
* один узел помечен как `Unschedulable`;
* для 19 узлов возник «**volume node affinity conflict**» — томы PVC/PV привязаны к конкретным зонам/узлам и не совпадают с местом, куда планировщик пытается поставить Pod.
  Поскольку **все** узлы были отфильтрованы, механизму preemption нечего «вытеснять», и он честно сообщает: *“Preemption is not helpful for scheduling”* ([datadoghq.com][1], [kubernetes.io][2]).

---

## Что именно означают сообщения планировщика

| Фрагмент сообщения                                                | Почему это возникает                                                                                                                                                                            | Тип решения                                                                |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `had untolerated taint {dedicated-node: clickhouse}`              | Узел зарезервирован для ClickHouse (Altinity рекомендует такой taint) ([docs.altinity.com][3])                                                                                                  | Добавьте toleration в Pod или уберите taint с узла                         |
| `had untolerated taint {node-role.kubernetes.io/control-plane: }` | C Kubernetes 1.24 master-узлы по умолчанию таинтятся `NoSchedule` ([kubernetes.io][4])                                                                                                          | Не размещайте рабочие поды на control-plane, либо явно добавьте toleration |
| `had untolerated taint {marketdata-test: true}`                   | Пользовательский taint вашей команды (тестовый кластерт)                                                                                                                                        | Точно так же — toleration или снятие taint                                 |
| `volume node affinity conflict`                                   | PV уже создан/забинден в другой зоне или на другом узле при `volumeBindingMode: Immediate` — планировщику нельзя прикрепить том к выбранному узлу ([stackoverflow.com][5], [help.coder.com][6]) |                                                                            |
| `were unschedulable`                                              | Узел находится в состоянии `SchedulingDisabled` (cordon/drain)                                                                                                                                  | `kubectl uncordon <node>`                                                  |

---

## 1. Проверяем taints и tolerations

1. Посмотреть список taint’ов на всех узлах:

   ```bash
   kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints
   ```
2. Добавить toleration в Pod/Deployment:

   ```yaml
   tolerations:
   - key: "dedicated-node"
     operator: "Equal"
     value: "clickhouse"
     effect: "NoSchedule"
   - key: "marketdata-test"
     operator: "Equal"
     value: "true"
     effect: "NoSchedule"
   ```

   Taints блокируют расписание, пока Pod не “потерпит” их — это базовый механизм из документации Kubernetes ([kubernetes.io][7], [cloudbolt.io][8]).

### Особый случай control-plane

Лучше **не** добавлять toleration к `node-role.kubernetes.io/control-plane`; вместо этого убедитесь, что есть рабочие worker-узлы без этого taint ([stackoverflow.com][9]).

---

## 2. Разбираем «volume node affinity conflict»

* Проверьте PVC и PV:

  ```bash
  kubectl get pvc,pv -o wide
  kubectl describe pv <pv-name>
  ```

  В `PV.spec.nodeAffinity` или `topology.kubernetes.io/zone` увидите, к какой зоне/узлу он привязан ([help.coder.com][10], [kubernetes.io][11]).
* Частые варианты исправления:

  * изменить `storageClass` так, чтобы `volumeBindingMode: WaitForFirstConsumer` — тогда PV создаётся **после** выбора узла;
  * удалить PVC/PV и дать кластера создать новый в правильной зоне;
  * использовать StatefulSet со строгим `podTopologySpread`/`nodeSelector`, чтобы под и том попадали в одну зону.

---

## 3. Снимаем состояние Unschedulable

```bash
kubectl get nodes | grep SchedulingDisabled
kubectl uncordon <node-name>
```

Если узел был «дренирован» для обслуживания, верните его в строй или исключите из выбора планировщика ([gremlin.com][12]).

---

## 4. Почему preemption не сработала

Preemption пытается вытеснить поды **только на узлах, которые прошли все фильтры кроме ресурсов**; если узел отфильтрован из-за taint или node-affinity тома, он вообще не рассматривается ([kubernetes.io][13]). Поэтому, пока вы не уберёте taint’ы и конфликт тома, вытеснять будет нечего.

---

## 5. Пошаговый чек-лист

1. **Снять cordon**: `kubectl uncordon <node>`, если нужен этот узел.
2. **Проверить/удалить лишние taint’ы** либо добавить toleration’ы, как показано выше.
3. **Проверить PVC/PV**: убедитесь, что зоны совпадают, или переключитесь на `WaitForFirstConsumer`.
4. Перезапустить Pod/Deployment (`kubectl delete pod <name>` — он пересоздастся) и убедиться, что статус стал `Running`.
5. Проверить события: `kubectl describe pod <name>` — ошибок FailedScheduling быть не должно.

---

## 6. Минимальный пример Deployment с toleration и без конфликта томов

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      tolerations:
      - key: dedicated-node
        operator: Equal
        value: clickhouse
        effect: NoSchedule
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: data-pvc
      containers:
      - name: app
        image: alpine
        command: ["sleep","3600"]
        volumeMounts:
        - mountPath: /data
          name: data
---
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/aws-ebs
volumeBindingMode: WaitForFirstConsumer
```

С такими настройками Pod «терпит» нужный таинт и PV будет создан в той же зоне, в которой планировщик выберет узел, исключив конфликт нодовой аффинности.

---

### Ключевые команды для ежедневной диагностики

```bash
# Сводка по таинтам
kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints

# Все Pending поды с причиной
kubectl get pods --all-namespaces --field-selector=status.phase=Pending -o wide

# Детали конкретного Pending Pod
kubectl describe pod <pod-name>

# Проверка событий кластера
kubectl get events --sort-by=.lastTimestamp
```

Следуя этому чек-листу, вы уберёте несовместимые taint’ы, поправите привязку томов и Pod перейдёт из `Pending` в `Running`.

[1]: https://www.datadoghq.com/blog/debug-kubernetes-pending-pods/?utm_source=chatgpt.com "Kubernetes pod pending failures: How to debug - Datadog"
[2]: https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/?utm_source=chatgpt.com "Pod Priority and Preemption - Kubernetes"
[3]: https://docs.altinity.com/altinitycloud/quickstartguide/running-in-your-cloud-byok/kubernetes-requirements/?utm_source=chatgpt.com "Kubernetes requirements | Altinity® Documentation"
[4]: https://kubernetes.io/docs/reference/labels-annotations-taints/?utm_source=chatgpt.com "Well-Known Labels, Annotations and Taints - Kubernetes"
[5]: https://stackoverflow.com/questions/51946393/kubernetes-pod-warning-1-nodes-had-volume-node-affinity-conflict?utm_source=chatgpt.com "Kubernetes Pod Warning: 1 node(s) had volume node affinity conflict"
[6]: https://help.coder.com/hc/en-us/articles/27670076918679-Resolving-Volume-Node-Affinity-Conflict-in-Kubernetes?utm_source=chatgpt.com "Resolving \"Volume Node Affinity Conflict\" in Kubernetes - Coder"
[7]: https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/?utm_source=chatgpt.com "Taints and Tolerations | Kubernetes"
[8]: https://www.cloudbolt.io/kubernetes-pod-scheduling/kubernetes-taints/?utm_source=chatgpt.com "Kubernetes Taints: Definitive Guide - CloudBolt"
[9]: https://stackoverflow.com/questions/77194853/pending-status-pod-unschedulable-untolerated-taint?utm_source=chatgpt.com "openshift - Pending Status | Pod Unschedulable | Untolerated Taint"
[10]: https://help.coder.com/hc/en-us/articles/27670076918679-Resolving-Volume-Node-Affinity-Conflict-in-Kubernetes "Resolving \"Volume Node Affinity Conflict\" in Kubernetes – Coder"
[11]: https://kubernetes.io/docs/concepts/storage/persistent-volumes/?utm_source=chatgpt.com "Persistent Volumes - Kubernetes"
[12]: https://www.gremlin.com/blog/how-to-fix-kubernetes-unschedulable-pods?utm_source=chatgpt.com "How to troubleshoot unschedulable Pods in Kubernetes - Gremlin"
[13]: https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/ "Pod Priority and Preemption | Kubernetes"
