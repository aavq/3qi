### Что показывает скрин-лог

Kiali каждые несколько секунд пытается «list / watch» объекты, которых **нет** в вашем `ClusterRole`.
По-строчно из лога (читаем после слова *resource*):

| API Group                   | Resource                                            |
| --------------------------- | --------------------------------------------------- |
| `networking.istio.io`       | **workloadgroups**                                  |
| `gateway.networking.k8s.io` | **referencegrants**, **httproutes**, **grpcroutes** |
| `telemetry.istio.io`        | **telemetries**                                     |
| `extensions.istio.io`       | **wasmplugins**                                     |

Сервис-аккаунт `system:serviceaccount:kiali:kiali` не имеет `list/watch` на эти ресурсы, поэтому kube-api возвращает `Forbidden`, а Kiali пишет `Failed to list … is forbidden`.

Gatekeeper при этом **успешно пропустил** обновлённую роль — но она просто оказалась неполной.

---

## Шаг 1. Соберите список недостающих ресурсов «автоматически»

```bash
# (1) Сохраняем свежий лог
kubectl logs deploy/kiali -n kiali --since=5m > /tmp/kiali.log

# (2) Выдёргиваем уникальные пары "<apigroup> <resource>"
grep -oP 'resource\\s+"[^"]+"' /tmp/kiali.log \
| awk '{print $2}' | tr -d '"' \
| sort -u
```

У вас должно получиться нечто вроде:

```
grpcroutes
httproutes
referencegrants
telemetries
wasmplugins
workloadgroups
```

---

## Шаг 2. Дописываем `ClusterRole kiali-viewer`

> **Важно:** всё ещё без wildcard — это полностью удовлетворяет
> Gatekeeper-констрейнту **policy-essentials-v2022-prohibit-role-wildcard-access**.

```yaml
# kiali/overlays/rbac-fix/clusterrole-patch.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kiali-viewer
$patch: merge
rules:
# --- Istio networking (добавили workloadgroups) -------------
- apiGroups: ["networking.istio.io"]
  resources:
    - workloadgroups           # NEW
    - destinationrules
    - gateways
    - virtualservices
    - serviceentries
    - sidecars
    - envoyfilters
    - workloadentries
  verbs: ["get","list","watch"]

# --- Istio telemetry ----------------------------------------
- apiGroups: ["telemetry.istio.io"]
  resources:
    - telemetries              # NEW
  verbs: ["get","list","watch"]

# --- Istio Wasm plugins -------------------------------------
- apiGroups: ["extensions.istio.io"]
  resources:
    - wasmplugins              # NEW
  verbs: ["get","list","watch"]

# --- Kubernetes Gateway API objects -------------------------
- apiGroups: ["gateway.networking.k8s.io"]
  resources:
    - httproutes               # NEW
    - grpcroutes               # NEW
    - referencegrants          # NEW
  verbs: ["get","list","watch"]
```

Сохраняем, коммитим в Git-репо, запускаем **Sync** в Argo CD.

---

## Шаг 3. Проверяем

```bash
# Pod должен перезапуститься (Argo или вручную)
kubectl rollout restart deploy/kiali -n kiali

# Через минуту смотрим, остались ли Forbidden
kubectl logs deploy/kiali -n kiali --since=2m | grep -i "is forbidden" || echo "Нет ошибок RBAC 🎉"
```

Если строк «is forbidden» больше нет — значит RBAC-прав хватило и Gatekeeper тоже доволен (ни одного wildcard’а).

---

## А если появятся новые `is forbidden`?

1. Повторите **Шаг 1** — иногда после устранения первой порции Kiali переходит к следующей.
2. Добавьте недостающие ресурсы в тот же patch-файл.

Набор CRD зависит от версии Istio / Gateway API; при апгрейде могут появляться новые типы (например `tlsroutes`, `tcproutes`).

---

## Альтернативные (но менее желательные) варианты

| Подход                                         | Что делать                                                                        | Комментарий                                              |
| ---------------------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------- |
| **Ослабить Gatekeeper только для этой роли**   | Добавить `spec.parameters.exemptions.clusterRoles: ["kiali-viewer"]` в Constraint | Самый быстрый, но политика для Kiali больше не действует |
| **Оставить wildcard, но только внутри группы** | Gatekeeper-шаблон не различает «scope» — любое `resources: ["*"]` запрещён        | Требуется менять Rego-шаблон: > 5-10 мин                 |
| **Label-исключение целого NS**                 | `kubectl label ns kiali admission.gatekeeper.sh/ignore=true`                      | Сбрасывает все политики Gatekeeper в namespace           |

---

### Итого

* Ошибки `cannot list resource … is forbidden` — это недостаточные RBAC.
* Gatekeeper больше не мешает; надо **дописать** отсутствующие ресурсы в `ClusterRole`.
* После добавления (`workloadgroups`, `telemetries`, `wasmplugins`, `httproutes`, `grpcroutes`, `referencegrants`) ошибки уходят, Kiali снова строит граф и метрики.


***
***
***


Ниже — «расширенная» **ClusterRole `kiali-viewer` без единого wildcard**, в которую включены **все объекты**, которые Kiali может читать в современном Kubernetes + Istio (≥ 1.20) и Gateway-API (v1beta1).
Она проходит Constraint **policy-essentials-v2022-prohibit-role-wildcard-access**, потому что в каждом правиле перечислены ресурсы явно.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kiali-viewer
  labels:
    app: kiali
rules:
# ------------------------------------------------------------------------------
# 1) Kubernetes «core» API (глобально и по-неймспейсово)
# ------------------------------------------------------------------------------
- apiGroups: [""]
  resources:
    - namespaces
    - nodes
    - services
    - endpoints
    - pods
    - pods/log
    - pods/portforward
    - replicationcontrollers
    - configmaps
    - events
  verbs: ["get", "list", "watch"]

# ------------------------------------------------------------------------------
# 2) Workloads
# ------------------------------------------------------------------------------
- apiGroups: ["apps"]
  resources:
    - deployments
    - replicasets
    - daemonsets
    - statefulsets
  verbs: ["get", "list", "watch"]

- apiGroups: ["batch"]
  resources:
    - jobs
    - cronjobs
  verbs: ["get", "list", "watch"]

- apiGroups: ["autoscaling"]
  resources:
    - horizontalpodautoscalers
  verbs: ["get", "list", "watch"]

# ------------------------------------------------------------------------------
# 3) Istio — networking.k8s.io
# ------------------------------------------------------------------------------
- apiGroups: ["networking.istio.io"]
  resources:
    - virtualservices
    - destinationrules
    - serviceentries
    - gateways
    - sidecars
    - envoyfilters
    - workloadentries
    - workloadgroups
    - proxyconfigs           # >= 1.21
  verbs: ["get", "list", "watch"]

# 4) Istio — security.istio.io
- apiGroups: ["security.istio.io"]
  resources:
    - authorizationpolicies
    - peerauthentications
    - requestauthentications
  verbs: ["get", "list", "watch"]

# 5) Istio — telemetry.istio.io
- apiGroups: ["telemetry.istio.io"]
  resources:
    - telemetries
  verbs: ["get", "list", "watch"]

# 6) Istio — extensions.istio.io  (Wasm-фильтры)
- apiGroups: ["extensions.istio.io"]
  resources:
    - wasmplugins
  verbs: ["get", "list", "watch"]

# ------------------------------------------------------------------------------
# 7) Gateway API (v1beta1)
# ------------------------------------------------------------------------------
- apiGroups: ["gateway.networking.k8s.io"]
  resources:
    - gatewayclasses
    - gateways
    - httproutes
    - tcproutes
    - tlsroutes
    - udproutes
    - grpcroutes
    - referencegrants
  verbs: ["get", "list", "watch"]

# ------------------------------------------------------------------------------
# 8) Собственные CRD Kiali (дешборды) — чтобы UI не ругался
# ------------------------------------------------------------------------------
- apiGroups: ["monitoring.kiali.io"]
  resources:
    - monitoringdashboards
  verbs: ["get", "list", "watch"]
```

---

### Как применять

1. **Добавьте** YAML в ваш Git-репозиторий, чтобы Argo CD/Helm применяли его *после* чарта Kiali-operator (он всё равно создаст «пустую» роль — ваш файл её перезапишет).
2. Убедитесь, что сервис-аккаунт пода Kiali остаётся тем же (`kiali:kiali`) — роль уже привязана через `ClusterRoleBinding kiali`.
3. Проверка:

   ```bash
   kubectl rollout restart deploy/kiali -n kiali
   kubectl logs -n kiali deploy/kiali --since=2m | grep -i "is forbidden" || echo "RBAC-ошибок нет 👍"
   ```

---

### Обновление при новых версиях Istio / Gateway-API

* Когда появляются новые CRD (например, `tcpRoute` → `tlsRoutes` в Gateway-API, `meshtraffics` в будущих релизах Istio), просто:

  1. посмотрите, на что жалуется лог Kiali (`cannot list resource … is forbidden`);
  2. добавьте эти ресурсы в соответствующее правило и сделайте `git commit` — Gatekeeper не будет против, пока wildcard’ов нет.

---

### Почему не оставили wildcard?

Constraint **`policy-essentials-v2022-prohibit-role-wildcard-access`** запрещает

```yaml
resources: ["*"]
```

в любых ClusterRole/Role.
Перечисляя ресурсы явно, мы:

* соблюдаем требование политики,
* сохраняем весь «read-only» функционал Kiali,
* минимально открываем доступ (только `get/list/watch`, без `create`/`update`/`delete`).

Эта роль подходит для production-кластеров, где RBAC должен быть строгим, а Gatekeeper — включённым.

