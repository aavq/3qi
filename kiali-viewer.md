Отличная идея: оставить **дефолтные** RBAC из Helm-чарта Kiali и сделать **точечное исключение** в Gatekeeper, чтобы не трогать остальной кластер.

Ниже — полностью воспроизводимая схема с меткой-исключением. Суть:

1. в **Constraint** добавляем `labelSelector` → правило применяется ко всем объектам **кроме** тех, у кого есть специальная метка;
2. в Helm-выводе Kiali **долейбливаем** `ClusterRole/ClusterRoleBinding` нужной меткой, чтобы правило их не касалось.

---

# 0) Как найти «тот самый» Constraint

```bash
# Какие виды constraints есть
kubectl api-resources --api-group=constraints.gatekeeper.sh

# Найти ваш — по имени из ошибки
kubectl get $(kubectl api-resources --api-group=constraints.gatekeeper.sh -o name | tr '\n' ',') -A \
  | grep -i 'prohibit-role-wildcard-access\|wildcard\|role'

# Посмотреть его YAML
kubectl -n <ns-constraint-if-any> get <KIND>/<NAME> -o yaml
```

В примерах ниже я буду называть его **`<WILDCARD_CONSTRAINT>`** (подставь свой Kind/Name, например `K8sDisallowWildcardRoles/policy-essentials-v2022-prohibit-role-wildcard-access`).

---

# 1) Патчим Constraint: добавляем исключение по метке

Выберем уникальный ключ, например:
`gatekeeper.kiali.io/ignore-wildcard: "true"`

Идея — **матчить только объекты, у которых эта метка отсутствует**. Тогда объекты с меткой будут исключены из проверки.

Минимальный патч (работает и для cluster-scoped объектов — `ClusterRole`, `ClusterRoleBinding`):

```yaml
# PATCH для вашего Constraint (НЕ Template!)
spec:
  match:
    # существующие match.* — сохранить!
    # добавляем фильтр по меткам:
    labelSelector:
      matchExpressions:
        - key: gatekeeper.kiali.io/ignore-wildcard
          operator: DoesNotExist
```

Применить можно так:

```bash
kubectl patch <KIND> <WILDCARD_CONSTRAINT_NAME> --type merge -p '{
  "spec": {
    "match": {
      "labelSelector": {
        "matchExpressions": [{
          "key": "gatekeeper.kiali.io/ignore-wildcard",
          "operator": "DoesNotExist"
        }]
      }
    }
  }
}'
```

> Почему `DoesNotExist`? Gatekeeper будет применять политику ко всем объектам, **где этой метки нет**. Мы добавим метку только на Kiali-RBAC → на них политика **не сработает**, остальной кластер остаётся защищён.

Альтернатива (если хотите временно увидеть только предупреждения): у конкретного Constraint можно задать

```yaml
spec:
  enforcementAction: warn
```

Но вы просили именно **точечное** исключение — оставляем `deny` и делаем метки.

---

# 2) Долейбливаем RBAC Kiali (Helm-chart остаётся дефолтным)

Вам нужно, чтобы финальные манифесты Kiali получили метку
`gatekeeper.kiali.io/ignore-wildcard: "true"` на:

* `ClusterRole/kiali`
* `ClusterRole/kiali-viewer`
* (опционально) соответствующие `ClusterRoleBinding` (иногда и они матчатся в правилах)

## Вариант A. Через Kustomize-патчи поверх Helm (удобно в ArgoCD)

В Application добавьте второй источник (или App-of-Apps). В kustomization.yaml:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - <путь/на/helm-выход, если multi-source не используется>
patches:
  - target:
      kind: ClusterRole
      name: kiali
    patch: |-
      - op: add
        path: /metadata/labels/gatekeeper.kiali.io~1ignore-wildcard
        value: "true"
  - target:
      kind: ClusterRole
      name: kiali-viewer
    patch: |-
      - op: add
        path: /metadata/labels/gatekeeper.kiali.io~1ignore-wildcard
        value: "true"
  - target:
      kind: ClusterRoleBinding
      name: kiali
    patch: |-
      - op: add
        path: /metadata/labels/gatekeeper.kiali.io~1ignore-wildcard
        value: "true"
  - target:
      kind: ClusterRoleBinding
      name: kiali-viewer
    patch: |-
      - op: add
        path: /metadata/labels/gatekeeper.kiali.io~1ignore-wildcard
        value: "true"
```

> Обрати внимание на `~1` в пути JSONPatch — экранирование `/` в ключе метки.

В ArgoCD можно выставить **sync-wave** так, чтобы патч применялся одновременно с Helm-выводом, а сам **Constraint** с labelSelector — синк-вейвом **раньше**, чтобы при синке RBAC уже попадали под «исключение»:

```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "-1"  # для Constraint
# ...
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "0"   # для Helm Kiali + патчи
```

## Вариант B. Helm postRenderer (если не используете Kustomize)

Добавьте postRenderer (kustomize) в Helm-источнике ArgoCD или используйте встроенный postRenderer в ArgoCD 2.6+ для добавления меток на выбранные объекты. Суть та же — добавить метку в `metadata.labels` нужных ресурсов.

---

# 3) Проверка

1. Убедиться, что Constraint теперь с `labelSelector`:

```bash
kubectl get <KIND> <WILDCARD_CONSTRAINT_NAME> -o jsonpath='{.spec.match.labelSelector}'
```

2. Синкануть Kiali:

```bash
argocd app sync <your-kiali-app>
```

3. Проверить, что метки появились:

```bash
kubectl get clusterrole kiali -o json | jq -r '.metadata.labels["gatekeeper.kiali.io/ignore-wildcard"]'
kubectl get clusterrole kiali-viewer -o json | jq -r '.metadata.labels["gatekeeper.kiali.io/ignore-wildcard"]'
kubectl get clusterrolebinding kiali -o json | jq -r '.metadata.labels["gatekeeper.kiali.io/ignore-wildcard"]'
```

4. Убедиться, что Gatekeeper не блокирует:

```bash
# В событиях kube-apiserver/argocd больше нет "wildcard" отказов
kubectl get events -A | grep -i gatekeeper | grep -i wildcard || echo "OK"
```

5. Kiali должен стартовать, роли применены, UI открывается. На всякий случай:

```bash
kubectl -n <ns-kiali> rollout restart deploy/kiali
kubectl -n <ns-kiali> logs deploy/kiali --since=2m | egrep -i 'forbidden|denied|wildcard' || echo "RBAC OK"
```

---

# 4) Что если ваш ConstraintTemplate уже умеет исключения?

Некоторые шаблоны из библиотек имеют параметры вроде:

```yaml
spec:
  parameters:
    exemptions:
      - kind: ClusterRole
        names: ["kiali","kiali-viewer"]
```

или списки `allowedResources`. Если в **вашем** `ConstraintTemplate` такие параметры есть — используйте их (это ещё чище, чем labelSelector). Но т.к. шаблоны часто разные, универсальный способ — **labelSelector + метки**, описанный выше.

---

# 5) Почему исключение работает и безопасно

* Мы **не ослабляем** политику для всего кластера, а исключаем **строго промаркированные** объекты.
* И `ClusterRole`, и `ClusterRoleBinding` — **кластерные** объекты; для них прекрасно работает `match.labelSelector`.
* Остальной трафик RBAC остаётся под тем же запретом wildcard.
* Отвязаться от кастомных ролей → проще сопровождать апгрейды Kiali (Helm-дефолты используются как есть).

---

# 6) Быстрый чек-лист внедрения

1. Найти и пропатчить **Constraint**: добавить `labelSelector DoesNotExist gatekeeper.kiali.io/ignore-wildcard`.
2. Включить в ArgoCD Sync-waves: Constraint (`-1`), Helm+патчи (`0`).
3. Добавить метку `gatekeeper.kiali.io/ignore-wildcard: "true"` на:

   * ClusterRole `kiali`, `kiali-viewer`
   * ClusterRoleBinding `kiali`, `kiali-viewer`
     (через Kustomize-patch или postRenderer)
4. `argocd app sync` → проверить, что роли применились и Gatekeeper не ругается.
5. Перезапустить Kiali и проверить UI/логи.

Если пришлёшь YAML вашего `<WILDCARD_CONSTRAINT>` и манифест ArgoCD Application, подготовлю конкретные патчи с sync-waves под ваш репозиторий.
