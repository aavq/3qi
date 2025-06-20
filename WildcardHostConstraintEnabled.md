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
