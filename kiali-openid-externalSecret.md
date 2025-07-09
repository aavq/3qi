```yaml
{{- if .Values.externalSecret.enabled }}
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {{ .Values.externalSecret.metadata.name | default "kiali-oidc" }}
  namespace: {{ .Values.externalSecret.metadata.namespace | default .Release.Namespace }}
  {{- with .Values.externalSecret.metadata.labels }}
  labels:
{{ toYaml . | nindent 4 }}
  {{- end }}
  {{- with .Values.externalSecret.metadata.annotations }}
  annotations:
{{ toYaml . | nindent 4 }}
  {{- end }}
spec:
  refreshInterval: {{ .Values.externalSecret.refreshInterval | default "10m" }}
  secretStoreRef:
    name: {{ .Values.externalSecret.secretStoreRef.name | default "kiali" }}
    kind: {{ .Values.externalSecret.secretStoreRef.kind | default "SecretStore" }}
  target:
    name: {{ .Values.externalSecret.target.name | default .Values.externalSecret.metadata.name | default "kiali" }}
    creationPolicy: {{ .Values.externalSecret.target.creationPolicy | default "Owner" }}
    template:
      type: {{ .Values.externalSecret.target.templateType | default "Opaque" }}
  data:
{{- range .Values.externalSecret.data }}
    - secretKey: {{ .secretKey }}
      remoteRef:
        key: {{ .remoteRefKey }}
        version: {{ default "latest" .version | quote }}
{{- end }}
{{- end }}
```


## Сводка

Я добавил в чарте файл `templates/externalsecret.yaml` (см. canvas) — именно он генерирует ресурс `ExternalSecret`.

* Ресурс создаётся **только** если `externalSecret.enabled=true`. Это реализовано через условный блок `{{- if .Values.externalSecret.enabled }}` —- стандартная техника в Helm для включения/выключения шаблонов ([helm.sh][1], [stackoverflow.com][2]).
* Все ключевые поля (имя, namespace, `refreshInterval`, `secretStoreRef`, `target`, список `data`) выводятся из `values.yaml`; если в values ничего не передано, подставляются безопасные значения по умолчанию через функцию `default` ([helm.sh][3]).
* Для `remoteRef.version` по умолчанию проставляется строка **"latest"** — это соответствует последней версии секрета в Google Secret Manager и поддерживается External-Secrets Operator ([external-secrets.io][4], [external-secrets.io][5]).

---

## Пример фрагмента `values.yaml`

```yaml
externalSecret:
  enabled: true          # Включить/выключить создание ресурса
  metadata:
    name: kiali-oidc     # Имя ExternalSecret (по умолчанию kiali-oidc)
    namespace: kiali     # Namespace (по умолчанию .Release.Namespace)
    labels: {}           # Доп-метки
    annotations: {}      # Доп-аннотации
  refreshInterval: 10m   # Как часто опрашивать внешний секрет
  secretStoreRef:
    name: kiali
    kind: SecretStore
  target:
    name: kiali          # Имя создаваемого kubernetes-секрета
    creationPolicy: Owner
    templateType: Opaque
  data:
    - secretKey: oidc-secret
      remoteRefKey: IDP_INTEGRATION_CLUSTER_01
      # version опционален; пусто или "latest" → последняя версия
```

### Что изменять чаще всего

| Поле                        | За что отвечает                | Какое значение ставить                                 |
| --------------------------- | ------------------------------ | ------------------------------------------------------ |
| `secretStoreRef.name`       | Какой SecretStore использовать | Имя SecretStore, где лежат креды к GSM                 |
| `data[*].remoteRefKey`      | Ключ секрета в GSM             | Например `IDP_INTEGRATION_CLUSTER_01`                  |
| `data[*].version` (необяз.) | Версия секрета в GSM           | Укажите конкретную (`"3"`) или опустите для `"latest"` |

---

## Как это работает под капотом

1. **External Secrets Operator** каждые `refreshInterval` секунд обращается к GSM через `SecretStoreRef`, забирает версию (`latest` либо указанную) и кладёт содержимое в `target`-Secret ([external-secrets.io][4], [external-secrets.io][6]).
2. Helm-функция `range` разворачивает любой список `data`, поэтому можно задать сразу несколько ключей-версий ([helm.sh][1]).
3. Вызов `default` гарантирует, что манифест соберётся даже при неполном `values.yaml` — одна из общих практик Helm ([helm.sh][3], [helm.sh][7]).

---

## Дальнейшие шаги

1. **Обновите** ваш файл `values.yaml` теми значениями, которые нужны для конкретного кластера/окружения.
2. **Установите** или **обновите** чарт:

   ```bash
   helm upgrade --install kiali ./my-chart -n kiali -f values.yaml
   ```
3. Убедитесь, что в namespace `kiali` появился объект `ExternalSecret` и связанный `Secret`.

Если потребуется доработать шаблон или добавить новые параметры — дайте знать, и мы расширим файл в canvas!

[1]: https://helm.sh/docs/chart_template_guide/control_structures/?utm_source=chatgpt.com "Flow Control - Helm"
[2]: https://stackoverflow.com/questions/57878785/helm-conditional-templates?utm_source=chatgpt.com "Helm Conditional Templates - kubernetes - Stack Overflow"
[3]: https://helm.sh/docs/chart_template_guide/functions_and_pipelines/?utm_source=chatgpt.com "Template Functions and Pipelines - Helm"
[4]: https://external-secrets.io/latest/api/externalsecret/?utm_source=chatgpt.com "ExternalSecret - External Secrets Operator"
[5]: https://external-secrets.io/v0.5.8/api-overview/?utm_source=chatgpt.com "API Overview - External Secrets Operator"
[6]: https://external-secrets.io/v0.8.1/api/externalsecret/?utm_source=chatgpt.com "ExternalSecret - External Secrets Operator"
[7]: https://helm.sh/docs/chart_template_guide/values_files/?utm_source=chatgpt.com "Values Files - Helm"
