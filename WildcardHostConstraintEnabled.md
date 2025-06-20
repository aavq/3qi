Ниже приведён минимальный, но полностью рабочий Helm-шаблон **templates/k8s-tenant-wildcard-host.yaml**.
Он создаёт ресурс `K8sTenantWildcardHost` только если в `values.yaml` установлен флаг `WildcardHostConstraint.enabled: true` и автоматически переносит все элементы из массива `values.domainSuffixes` в `spec.parameters.domainSuffixes`.

```yaml
{{- /*
templates/k8s-tenant-wildcard-host.yaml
Creates a Gatekeeper Constraint (kind: K8sTenantWildcardHost)
only when WildcardHostConstraint.enabled is true.
*/ -}}
{{- if .Values.WildcardHostConstraint.enabled }}
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sTenantWildcardHost
metadata:
  name: {{ .Values.WildcardHostConstraint.name | default "tenant-wildcard-hosts" | quote }}
  labels:
    app.kubernetes.io/managed-by: helm
    {{- with .Values.WildcardHostConstraint.extraLabels }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
spec:
  parameters:
    domainSuffixes:
    {{- if not (hasKey .Values "domainSuffixes") }}
    # <-- пустой список: Helm вернёт ошибку; добавьте элементы в values.yaml
    {{- else }}
    {{- range .Values.domainSuffixes }}
    - "{{ . }}"
    {{- end }}
    {{- end }}
  match:
    kinds:
      - apiGroups: ["networking.istio.io"]
        kinds: ["Gateway"]
{{- end }}
```

### Как использовать

1. **`values.yaml`**

   ```yaml
   WildcardHostConstraint:
     enabled: true
     # name и extraLabels необязательны:
     # name: tenant-wildcard-hosts-prod
     # extraLabels:
     #   environment: prod

   domainSuffixes:
     - asm-uk-01.uat.hc.intranet.corp.com
     - asm-uk-01.prod.hc.intranet.corp.com
   ```

2. **Деплой**

   ```bash
   helm upgrade --install wildcard-gatekeeper ./my-chart
   ```

3. Если нужно выключить политику, достаточно изменить значение

   ```yaml
   WildcardHostConstraint:
     enabled: false
   ```

   и выполнить `helm upgrade`; объект-Constraint будет удалён (Helm применит manifest diff).

> **Важно:** сам `ConstraintTemplate` (`k8stenantwildcardhost`) должен быть установлен в кластере до (или вместе с) этого чарта; обычно его кладут в папку `templates/` отдельным YAML-файлом без условного блока, либо управляют через другой релиз Helm/Argo-CD.



---
---
---


Below is a ready-to-drop Helm template that **reads all policy-related settings from a single root map called `policies`**, plus the matching `values.yaml` fragment.
The chart:

* renders the **`K8sTenantWildcardHost` Constraint** only when `policies.k8sTenantWildcardHost.enabled` is `true`;
* supports any number of DNS suffixes via the array `policies.k8sTenantWildcardHost.domainSuffixes`;
* keeps extra knobs (`name`, `extraLabels`) under the same policy branch.

---

## Updated `values.yaml`

```yaml
policies:
  k8sTenantWildcardHost:
    enabled: true            # switch the resource on/off
    name: tenant-wildcard-hosts
    extraLabels:             # optional
      environment: uat
    domainSuffixes:
      - asm-uk-01.uat.hc.intranet.corp.com
      - asm-uk-01.prod.hc.intranet.corp.com
```

*Putting all policy toggles under one map is a recommended pattern for large charts because it avoids value-name collisions and groups related settings logically* ([helm.sh][1]).

---

## Updated Helm template

`templates/k8s-tenant-wildcard-host.yaml`

```yaml
{{- /*
Render a Gatekeeper Constraint only when
policies.k8sTenantWildcardHost.enabled is true.
*/ -}}
{{- $cfg := .Values.policies.k8sTenantWildcardHost | default dict -}}
{{- if ($cfg.enabled | default false) }}
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sTenantWildcardHost
metadata:
  name: {{ $cfg.name | default "tenant-wildcard-hosts" | quote }}
  labels:
    app.kubernetes.io/managed-by: helm
{{- with $cfg.extraLabels }}
{{ toYaml . | nindent 4 }}
{{- end }}
spec:
  parameters:
    domainSuffixes:
{{- /* render each suffix */ -}}
{{- range $cfg.domainSuffixes }}
      - "{{ . }}"
{{- end }}
  match:
    kinds:
      - apiGroups: ["networking.istio.io"]
        kinds: ["Gateway"]
{{- end }}
```

### What changed and why

| Change                                                  | Purpose                                                             | Helm reference                                            |                                                                      |
| ------------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------- |
| `{{- $cfg := .Values.policies.k8sTenantWildcardHost }}` | Short alias to nested map for cleaner code                          | Values object hierarchy ([helm.sh][2])                    |                                                                      |
| \`if (\$cfg.enabled                                     | default false)\`                                                    | Conditionally render manifest only when policy is enabled | Flow-control actions `if/else` ([helm.sh][3])                        |
| `range $cfg.domainSuffixes`                             | Loop through every suffix and emit a list item                      | `range` looping construct ([helm.sh][3])                  |                                                                      |
| \`toYaml .                                              | nindent 4\`                                                         | Dump arbitrary labels map with correct indentation        | Sprig `toYaml` & `nindent` functions ([helm.sh][4], [v2.helm.sh][5]) |
| All keys live under `policies`                          | Centralises feature flags; avoids clashes with other chart settings | Best-practice grouping of values ([helm.sh][1])           |                                                                      |

---

## How to test the change quickly

1. **Render templates locally**

   ```bash
   helm template wildcard ./my-chart \
     --values values.yaml | less
   ```

   Using `helm template` lets you review the generated CR before touching the cluster ([medium.com][6], [medium.com][7]).

2. **Toggle the flag**
   Set `policies.k8sTenantWildcardHost.enabled: false` and re-render; the manifest should disappear—confirming the condition works ([medium.com][8]).

3. **Dry-run install**

   ```bash
   helm install wildcard ./my-chart --dry-run --debug
   ```

   Validates syntax and that the CRD reference is resolved at deploy time ([helm.sh][9], [helm.sh][10]).

---

### Keep in mind

* The **ConstraintTemplate** for `K8sTenantWildcardHost` must already exist in the cluster (or be shipped in the same chart) so the generated Constraint can bind to it correctly ([helm.sh][11]).
* Nesting does **not** affect sub-charts automatically; if this policy sits in a parent chart, expose the same `policies` tree through `values.yaml` so sub-charts inherit it via `.Values.global` or explicit `import-values` blocks ([helm.sh][12]).

With these tweaks the chart stays idiomatic and scalable while giving you one clear place—`policies.*`—to enable or tune every admission-control rule.

[1]: https://helm.sh/docs/chart_best_practices/values/?utm_source=chatgpt.com "Values - Helm"
[2]: https://helm.sh/docs/chart_template_guide/values_files/?utm_source=chatgpt.com "Values Files - Helm"
[3]: https://helm.sh/docs/chart_template_guide/control_structures/?utm_source=chatgpt.com "Flow Control - Helm"
[4]: https://helm.sh/docs/chart_template_guide/function_list/?utm_source=chatgpt.com "Template Function List - Helm"
[5]: https://v2.helm.sh/docs/charts_tips_and_tricks/?utm_source=chatgpt.com "Chart Development Tips and Tricks - Helm v2"
[6]: https://medium.com/%40zparnold/why-im-a-fan-of-helm-template-over-helm-install-dc35a05115cf?utm_source=chatgpt.com "Why I'm a fan of `helm template` over `helm install` | by Zach Arnold"
[7]: https://medium.com/%40flaviuscdinu93/helm-basic-tutorial-streamline-kubernetes-deployments-at-scale-e88ab8ee59b9?utm_source=chatgpt.com "Helm Basic Tutorial: Streamline Kubernetes Deployments at Scale"
[8]: https://medium.com/%40michamarszaek/quality-gate-for-helm-charts-f260f5742198?utm_source=chatgpt.com "Quality gate for helm charts - Medium"
[9]: https://helm.sh/docs/howto/charts_tips_and_tricks/?utm_source=chatgpt.com "Chart Development Tips and Tricks - Helm"
[10]: https://helm.sh/docs/intro/using_helm/?utm_source=chatgpt.com "Using Helm"
[11]: https://helm.sh/docs/chart_best_practices/custom_resource_definitions/?utm_source=chatgpt.com "Custom Resource Definitions - Helm"
[12]: https://helm.sh/docs/chart_template_guide/subcharts_and_globals/?utm_source=chatgpt.com "Subcharts and Global Values - Helm"


---
---
---


## Итоговое изменение пути к данным values

Теперь все настройки лежат по пути
`.Values.constraint.policies.<policy-kind>`
поэтому шаблон должен читать параметры именно оттуда.
Ниже — готовые куски **values.yaml** и **templates/k8s-tenant-wildcard-host.yaml** (Helm v3), полностью учитывающие новое расположение данных.

---

## Новый `values.yaml`

```yaml
constraint:
  policies:
    k8sTenantWildcardHost:          # ← имя политики = ключ мапы
      enabled: true                 # включить/выключить Constraint
      name: tenant-wildcard-hosts   # (необязательно) кастомное имя CR
      extraLabels:                  # (необязательно) любые доп-метки
        environment: uat
      domainSuffixes:
        - asm-uk-01.uat.hc.intranet.corp.com
        - asm-uk-01.prod.hc.intranet.corp.com
```

*При желании добавляйте рядом другие политики, например `k8sUniqueIngressHost`, — структура «одна мапа `constraint.policies` → несколько политик» масштабируется без конфликтов.*

---

## Обновлённый Helm-шаблон

`templates/k8s-tenant-wildcard-host.yaml`

```yaml
{{- /*
Creates a Gatekeeper Constraint (K8sTenantWildcardHost) only when
constraint.policies.k8sTenantWildcardHost.enabled is true.
*/ -}}

{{- $cfg := .Values.constraint.policies.k8sTenantWildcardHost | default dict -}}
{{- if ($cfg.enabled | default false) }}
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sTenantWildcardHost
metadata:
  name: {{ $cfg.name | default "tenant-wildcard-hosts" | quote }}
  labels:
    app.kubernetes.io/managed-by: helm
{{- with $cfg.extraLabels }}
{{ toYaml . | nindent 4 }}
{{- end }}
spec:
  parameters:
    domainSuffixes:
{{- range $cfg.domainSuffixes }}
      - "{{ . }}"
{{- end }}
  match:
    kinds:
      - apiGroups: ["networking.istio.io"]
        kinds: ["Gateway"]
{{- end }}
```

### Что изменилось по сравнению с прошлой версией

| Раньше                                                        | Теперь                                              |
| ------------------------------------------------------------- | --------------------------------------------------- |
| `.Values.policies.k8sTenantWildcardHost`                      | `.Values.constraint.policies.k8sTenantWildcardHost` |
| Переменная-сокращение `{{- $cfg := .Values.policies... }}`    | `{{- $cfg := .Values.constraint.policies... }}`     |
| Все остальные блоки (`if`, `range`, `toYaml`) — без изменений | —                                                   |

---

## Проверка

```bash
# вывести рендер для контроля
helm template wildcard ./my-chart --values values.yaml | less

# при enabled: false объект не выводится
helm template wildcard ./my-chart \
  --set constraint.policies.k8sTenantWildcardHost.enabled=false
```

После применения (`helm upgrade --install …`) Gatekeeper начнёт отклонять «плохие» Gateway-ресурсы, пользуясь новым Constraint-ом.


