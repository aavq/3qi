Короткий ответ: **ConstraintTemplate трогать не нужно.**
Исключения для Kiali добавляются в **Constraint**, который использует шаблон `K8sProhibitRoleWildcardAccess`, через поле `spec.parameters.exemptions`. Шаблон официально поддерживает исключения по именам ClusterRole/Role и даже **regexMatch** для имён — это как раз ваш случай. ([Google Cloud][1])

Ниже — пошагово, как это сделать “по-взрослому” с ArgoCD.

---

# 1) Найти действующий Constraint и проверить, что это нужный шаблон

```bash
# посмотреть есть ли такие констрейнты (кейс-сенситивный kind!)
kubectl get k8sprohibitrolewildcardaccess.constraints.gatekeeper.sh -A

# если найден, показать YAML (запомните namespace/имя)
kubectl get k8sprohibitrolewildcardaccess.constraints.gatekeeper.sh <NAME> -n <NS> -o yaml
```

Если у вас применён **Policy Essentials v2022** от Anthos, такой Constraint обычно уже есть (имя наподобие `policy-essentials-v2022-prohibit-role-wildcard-access`). ([Google Cloud][2])

> Если **нет** ни одного Constraint — просто создайте свой (пример в §3).

---

# 2) Что именно добавить: exemptions (точечные исключения)

Шаблон `K8sProhibitRoleWildcardAccess` поддерживает:

* `parameters.exemptions.clusterRoles`: список кластерных ролей, каждая с `name:` и опционально `regexMatch: true` (тогда `name` — это регулярное выражение);
* `parameters.exemptions.roles`: список namespaced-ролей (name + namespace). ([Google Cloud][1])

Для Kiali из Helm-чарта вам, как правило, достаточно **кластерных** исключений:

* `kiali`
* `kiali-viewer`
  (если у вас канарейка — удобно одной regex закрыть варианты `kiali`, `kiali-viewer`, `kiali-canary`, `kiali-viewer-canary` и т.п.)

### Пример **PATCH** существующего Constraint (kubectl)

> Подставьте ваше `<NAME>`/`<NS>`.

```bash
kubectl patch k8sprohibitrolewildcardaccess.constraints.gatekeeper.sh <NAME> -n <NS> \
  --type merge -p '{
  "spec": {
    "parameters": {
      "exemptions": {
        "clusterRoles": [
          { "name": "^kiali(-viewer)?(-[a-z0-9-]+)?$", "regexMatch": true }
        ]
      }
    }
  }
}'
```

* Регекс выше пропускает `kiali`, `kiali-viewer`, а также их варианты с суффиксами (`-canary`, `-prod`, и т.п.). Поле `regexMatch: true` — **официально поддерживается** этим шаблоном. ([Google Cloud][1])

---

# 3) Если Constraint отсутствует — создайте свой (Git/ArgoCD)

В репозитории политик добавьте, например, `constraints/k8sprohibitrolewildcardaccess-kiali.yaml`:

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sProhibitRoleWildcardAccess
metadata:
  name: prohibit-role-wildcard-access
spec:
  enforcementAction: deny   # или оставьте по умолчанию
  match:
    # (обычно хватает умолчаний; шаблон сам таргетит Roles/ClusterRoles)
    # при желании можно уточнить kinds/scope
    kinds:
      - apiGroups: ["rbac.authorization.k8s.io"]
        kinds: ["ClusterRole","Role"]
  parameters:
    exemptions:
      clusterRoles:
        - name: "^kiali(-viewer)?(-[a-z0-9-]+)?$"
          regexMatch: true
```

Коммит → `argocd app sync <policy-app>`.

---

# 4) Привязка к релизу Kiali и проверка в ArgoCD

1. В **Kiali Helm values** включите генерацию дефолтных RBAC:

```yaml
rbac:
  create: true
deployment:
  cluster_wide_access: true
```

2. Убедитесь, что SA контроллера ArgoCD **может** создавать `ClusterRole/ClusterRoleBinding`.
3. Синканите приложение Kiali. Новые роли (`kiali`, `kiali-viewer`) создадутся от Helm и **пройдут** политику благодаря exemptions.
4. Проверка:

```bash
kubectl get clusterrole kiali kiali-viewer
kubectl get events -A | grep -i gatekeeper | grep -i wildcard || echo "OK"
```

---

# 5) Альтернатива без правки Constraints: labelSelector в Constraint (менее предпочтительно)

Если вы не хотите трогать параметры, можно исключить объекты с определённой меткой через `spec.match.labelSelector`:

```yaml
spec:
  match:
    labelSelector:
      matchExpressions:
        - key: gatekeeper.kiali.io/ignore-wildcard
          operator: DoesNotExist
```

Тогда добавьте метку к нужным `ClusterRole/ClusterRoleBinding` Kiali (Kustomize-патч или postRenderer Helm). Но раз шаблон уже **умеет exemptions**, лучше использовать именно **`parameters.exemptions`**, это чище и явнее. ([open-policy-agent.github.io][3])

---

# 6) Почему это безопасно

* Исключения действуют **точечно** по именам ролей Kiali и не ослабляют политику для остальных.
* Это стандартный механизм шаблона (`exemptions`), поддерживаемый в официальной библиотеке Policy Controller/Anthos. ([Google Cloud][1])

---

# 7) Быстрый чек-лист

* [ ] Найти/создать Constraint `K8sProhibitRoleWildcardAccess`.
* [ ] Добавить в `spec.parameters.exemptions.clusterRoles` исключение для Kiali (лучше **regex**). ([Google Cloud][1])
* [ ] Включить `rbac.create: true` и `cluster_wide_access: true` в values Kiali.
* [ ] Проверить права ArgoCD на ClusterRole/Binding.
* [ ] `argocd app sync` для политик, затем для Kiali.
* [ ] Проверить события Gatekeeper и запуск Kiali.

Если пришлёшь YAML вашего действующего Constraint (или ссылку на папку с политиками в Git), подготовлю **готовый patch** с вашим `metadata.name` и правильной regex-маской под ваши имена ролей (`kiali`, `kiali-viewer`, `kiali-canary`, и т.п.).

[1]: https://cloud.google.com/kubernetes-engine/enterprise/policy-controller/docs/latest/reference/constraint-template-library "Constraint template library  |  Policy Controller  |  Google Cloud"
[2]: https://cloud.google.com/kubernetes-engine/enterprise/policy-controller/docs/how-to/using-policy-essentials-v2022?utm_source=chatgpt.com "Use Policy Essentials v2022 policy constraints"
[3]: https://open-policy-agent.github.io/gatekeeper/website/docs/constrainttemplates/?utm_source=chatgpt.com "Constraint Templates | Gatekeeper - GitHub Pages"
