Below is a step-by-step way to get Kiali running again **without violating the Gatekeeper constraint *policy-essentials-v2022-prohibit-role-wildcard-access*** and without disabling the policy for the whole cluster.

---

## 1  Понять причину

* Kiali-operator в режиме *view only* создаёт `ClusterRole kiali-viewer` со строкой
  `resources: ["*"]` для групп `networking.istio.io` и `security.istio.io`.
* Шаблон Gatekeeper **K8sProhibitRoleWildcardAccess** запрещает любые `*` в `resources`, кроме явно перечисленных в исключениях.
* Поэтому admission-webhook даёт ошибку 403, и Argo CD не может применить манифест.

---

## 2  Что можно сделать

| Способ                                                                               | Когда уместно                                                | Плюсы                              | Минусы                                           |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------ | ---------------------------------- | ------------------------------------------------ |
| **A. Внести `kiali-viewer` в исключения** <br>(`parameters.exemptions.clusterRoles`) | Вы доверяете wildcard и хотите «как было»                    | 1--2 минуты работы                 | Политика перестаёт работать именно для этой роли |
| **B. Сформировать «безопасный» ClusterRole без `*`**                                 | Вы хотите соблюсти политику и получить весь функционал Kiali | Полностью совместимо с Gatekeeper  | Нужно перечислить ресурсы вручную                |
| **C. Пометить namespace `kiali` лейблом `admission.gatekeeper.sh/ignore`**           | Kiali в отдельном кластере наблюдения                        | Не трогает политику в остальных NS | Политика не проверяет всё, что находится в NS    |

Ниже приведена детальная инструкция для **варианта B** (рекомендуемый), а в конце — короткие примеры для A и C.

---

## 3  Собираем минимальные права Kiali

Kiali-документация описывает, что для логина нужен хотя бы `get namespaces`; для полноценного UI нужны read-доступы к объектам ядра Kubernetes и CRD Istio.

### 3.1 Список ресурсов без `*`

Ниже показаны ресурсы, которые исходный `kiali-viewer` запрашивает; мы просто сделали их явными и убрали wildcard:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kiali-viewer
  labels:
    app: kiali
rules:
# --- core ---
- apiGroups: [""]
  resources:
    - namespaces
    - pods
    - pods/log
    - pods/portforward
    - services
    - endpoints
    - replicationcontrollers
    - configmaps
  verbs: ["get", "list", "watch"]

# --- apps / batch ---
- apiGroups: ["apps","extensions"]
  resources: [deployments, replicasets, daemonsets, statefulsets]
  verbs: ["get","list","watch"]
- apiGroups: ["batch"]
  resources: [jobs, cronjobs]
  verbs: ["get","list","watch"]

# --- Istio networking ---
- apiGroups: ["networking.istio.io"]
  resources:
    - destinationrules
    - gateways
    - virtualservices
    - serviceentries
    - sidecars
    - envoyfilters
    - workloadentries
  verbs: ["get","list","watch"]

# --- Istio security ---
- apiGroups: ["security.istio.io"]
  resources:
    - authorizationpolicies
    - requestauthentications
    - peerauthentications
  verbs: ["get","list","watch"]

# --- Kiali CRDs ---
- apiGroups: ["monitoring.kiali.io"]
  resources: [monitoringdashboards]
  verbs: ["get","list","watch"]

# --- OpenShift-специфичное, оставляем если нужно ---
# - apiGroups: ["route.openshift.io","apps.openshift.io","project.openshift.io"] …
```

* Если вы используете только Kubernetes / GKE, блоки OpenShift можно удалить — тогда шаблон станет заметно короче.
* Полный список привилегий в оригинальном файле можно всегда вывести командой
  `kubectl describe clusterrole kiali-viewer` на тестовом кластере.

### 3.2 Деплой через Argo CD

Создайте оверлей или patch в вашем репозитории Git:

```yaml
# kiali/overlays/rbac-fix/clusterrole-patch.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kiali-viewer
$patch: replace
rules:
  # вставьте сюда содержимое из предыдущего раздела
```

Argo CD применит готовую роль; wildcard больше нет, и Gatekeeper пропустит ресурс.

---

## 4  Альтернативы

### 4.1  Добавить исключение в Constraint

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sProhibitRoleWildcardAccess
metadata:
  name: prohibit-role-wildcard-access
spec:
  parameters:
    exemptions:
      clusterRoles:
        - name: kiali-viewer
```

Шаблон `exemptions.clusterRoles` поддерживается официально.

### 4.2  Сделать namespace «невидимым» для Gatekeeper

```bash
kubectl label namespace kiali admission.gatekeeper.sh/ignore=true
```

Gatekeeper официально описывает способ исключать неймспейсы этим лейблом.

> **Важно:** namespace должен быть добавлен в список `exemptNamespaces` при установке Gatekeeper; иначе лейбл не сработает.

---

## 5  Проверка

1. **Gatekeeper audit** — убедитесь, что нет новых нарушений
   `kubectl get k8sprohibitrolewildcardaccess -A` → `.status.totalViolations` = 0.
2. **Argo CD** — синхронизация приложения должна пройти успешно (status = Synced).
3. **Kiali** — в UI нет красных баннеров про RBAC, граф и списки загружаются.

---

## 6  Что запомнить

* Gatekeeper запрещает `resources: ["*"]`; Kiali-viewer использует wildcard для групп Istio.
* Либо **уберите wildcard**, либо **добавьте исключение**, либо **исключите namespace**.
* Минимальный набор ресурсов для Kiali-viewer легко получить из оригинального кода Helm-чарта Kiali; явная спецификация ресурсов полностью удовлетворяет политике Gatekeeper и сохраняет функции Kiali.

Следуя шагам выше, вы избавитесь от ошибок `E0710 … prohibit-role-wildcard-access` в логах и восстановите работу Kiali, не ослабляя при этом общую безопасность RBAC-политик.
