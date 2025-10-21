Ниже — 2 рабочих пути для Kiali 2.15 (установлен в namespace `kiali`), чтобы он **видел только те неймспейсы, где реально есть Istio-нагрузки**, и при этом **список обновлялся автоматически** при добавлении/удалении неймспейсов.

> С релиза **Kiali 2.0 старый параметр `deployment.accessible_namespaces` больше не поддерживается**. Вместо него используются **cluster-wide access** и **discovery selectors**. Если вы всё ещё ищете `accessible_namespaces: ["**"]` — это уже прошлое. ([kiali.io][1])

---

# Вариант A (проще): Helm chart **kiali/kiali-server**

(кластерные права + селекторы для видимости)

**Почему так:** server-chart **не создаёт namespace-scoped Roles** по селекторам, значит ему нужен **cluster-wide** доступ; селекторы ограничат **видимые** в UI namespaces (динамически). ([kiali.io][1])

1. `values.yaml` для `kiali/kiali-server` (установлен в `kiali`):

```yaml
deployment:
  namespace: kiali
  # Для server-chart желательно оставить cluster-wide включённым
  cluster_wide_access: true

  # Список discovery selectors определяет, какие NS будут ВИДНЫ в Kiali
  # Покроем оба типовых случая автоинъекции: "classic" и "revisioned".
  discovery_selectors:
    default:
      - matchLabels:
          istio-injection: "enabled"     # classic auto-injection
      - matchExpressions:                # revision-based auto-injection
        - key: istio.io/rev
          operator: Exists
      # Если используете Ambient, раскомментируйте:
      # - matchLabels:
      #     istio.io/dataplane-mode: ambient
```

2. Установка/обновление:

```bash
helm repo add kiali https://kiali.org/helm-charts
helm upgrade -n kiali --install kiali-server kiali/kiali-server -f values.yaml
```

3. Динамика:
   Когда вы **помечаете** новый namespace под Istio (например, `istio-injection=enabled` или добавляете `istio.io/rev=1-22`), он **автоматически появится** в списке namespaces Kiali (за счёт селекторов и watch’ей). Системные `kube-*` и т.п. не будут показываться, если селекторы пустые; при явных селекторах вы и так показываете только «свои» NS. ([kiali.io][1])

> Примечание: Kiali **не читает селекторы из Istio MeshConfig** — задайте в Kiali **те же селекторы**, что и в Istio, вручную (как выше). ([kiali.io][1])

---

# Вариант B (жёстче по безопасности): Helm chart **kiali-operator** + Kiali CR

(пер-namespace Roles, автоподхват новых NS через reconcile)

**Почему так:** оператор умеет, при `cluster_wide_access: false`, **создавать Roles** только в тех неймспейсах, которые совпали по селекторам. Это уменьшает права Kiali до нужного минимума. ([kiali.io][1])

1. Устанавливаем оператор (важно: дать ему право создавать ClusterRoles при необходимости):

```bash
helm upgrade -n kiali-operator --create-namespace --install kiali-operator kiali/kiali-operator \
  --set clusterRoleCreator=true
```

2. Создаём CR `Kiali` в `kiali`:

```yaml
# kiali-cr.yaml
apiVersion: kiali.io/v1alpha1
kind: Kiali
metadata:
  name: kiali
  namespace: kiali
  annotations:
    # Чтобы оператор периодически пересматривал список NS (автоподхват новых):
    ansible.sdk.operatorframework.io/reconcile-period: 60s
spec:
  deployment:
    cluster_wide_access: false     # безопасность: без глобальных прав
    discovery_selectors:
      default:
        - matchLabels:
            istio-injection: "enabled"
        - matchExpressions:
          - key: istio.io/rev
            operator: Exists
        # - matchLabels: { istio.io/dataplane-mode: ambient }  # если нужно
```

```bash
kubectl apply -f kiali-cr.yaml
```

3. Динамика:
   Оператор будет **переустанавливать роли** по CR (каждые 60 секунд по аннотации выше, либо при любых изменениях CR/аннотаций/создании NS), подхватывая **новые/удалённые** соответствующие неймспейсы. ([kiali.io][1])

> Важно: если Istio control plane находится НЕ в `kiali`, его namespace тоже должен совпасть по вашим селекторам, иначе дайте ему дополнительную метку и включите её в селекторы (Kiali должен иметь доступ к control plane). ([kiali.io][1])

---

## Часто нужные команды

Пометить namespace под классическую автоинъекцию:

```bash
kubectl label ns my-app istio-injection=enabled --overwrite
```

Пометить namespace под ревизию:

```bash
kubectl label ns my-app istio.io/rev=1-22 --overwrite
```

Принудительно «ткнуть» оператор на reconcile (если не хотите ждать период):

```bash
kubectl annotate kiali kiali -n kiali --overwrite trigger-reconcile="$(date)"
```

([kiali.io][1])

---

## Краткое резюме выбора

* **Нужен минимум телодвижений** → **Вариант A (server-chart + cluster-wide + discovery selectors)**.
* **Нужны минимальные права (RBAC по NS)** → **Вариант B (operator + CR + discovery selectors + reconcile)**.

Обе схемы **автоматически** подхватывают новые неймспейсы за счёт селекторов (и reconciliation в варианте с оператором). Подробности — в актуальной документации по управлению неймспейсами в Kiali 2.x. ([kiali.io][1])

Если хочешь, могу сгенерировать готовые манифесты под твою сетку ревизий (`istio.io/rev`), control plane и изоляцию служебных NS.

[1]: https://kiali.io/docs/configuration/namespace-management/ "Namespace Management | Kiali"
