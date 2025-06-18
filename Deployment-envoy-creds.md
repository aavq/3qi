Ниже 👇 — сводка и готовый фрагмент шаблона Deployment, который добавляет `volumes` и `volumeMounts`, если в `values.yaml` присутствует блок `oauth-filter`.  Главные идеи:

* **Проверяем наличие ключей через `if / with`.**  Так шаблон выводит блоки только когда они заданы ([helm.sh][1]).
* **Ключи-с-дефисами читаем через `index`**, иначе `.`-нотация не работает ([stackoverflow.com][2], [github.com][3]).
* **Списки сериализуем `toYaml | nindent`** — это обеспечивает  корректное форматирование и отступы ([helm.sh][4], [github.com][5]).
* **`volumes` располагаем на том же уровне, что `containers`, а `volumeMounts` — внутри контейнера** — иначе манифест не пройдет валидацию ([stackoverflow.com][6]).
* Подход масштабируется: можно добавлять другие «опциональные» блоки (Init-контейнеры, аннотации и т. д.) теми же приёмами ([stackoverflow.com][7], [helm.sh][8]).

---

## 1 Пример `values.yaml`

```yaml
oauth-filter:
  volumes:
    - name: envoy-creds
      secret:
        secretName: envoy-oauth-secrets
        defaultMode: 0440
  volumeMounts:
    - name: envoy-creds
      mountPath: /etc/istio/creds
      readOnly: true
```

## 2 Фрагмент `templates/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "mychart.fullname" . }}
  labels: {{- include "mychart.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels: {{- include "mychart.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels: {{- include "mychart.selectorLabels" . | nindent 8 }}
    spec:
{{- /* ---------- Volumes (если заданы) ---------- */}}
{{- with (index .Values "oauth-filter") }}
{{- if .volumes }}
      volumes:
{{ toYaml .volumes | nindent 8 }}
{{- end }}
{{- end }}
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
{{- /* ------ VolumeMounts (если заданы) ------ */}}
{{- with (index .Values "oauth-filter") }}
{{- if .volumeMounts }}
          volumeMounts:
{{ toYaml .volumeMounts | nindent 12 }}
{{- end }}
{{- end }}
          ports:
            - containerPort: 8080
```

### Что здесь важно

1. **`with (index .Values "oauth-filter")`** — заходит в контекст под-карты и делает код короче ([stackoverflow.com][2]).
2. **Двойная проверка**: если `volumes` или `volumeMounts`-массив пуст, секции не выводятся ([kodekloud.com][9]).
3. **`nindent 8` / `nindent 12`** — число соответствует требуемому уровню отступа внутри Deployment. Это показано в рабочих примерах Helm-сообщества ([gist.github.com][10], [medium.com][11]).

---

## 3 Как протестировать

```bash
helm template myrelease ./mychart \
  --values values.yaml | yq eval '.spec.template.spec' -
```

* Без блока `oauth-filter`  секций не будет.
* При наличии — они появятся ровно как в `values.yaml`.

Такой шаблон легко расширяется: если завтра появятся, например, `initContainers`, достаточно добавить ещё один `with` / `if`-блок по аналогии.

[1]: https://helm.sh/docs/chart_template_guide/control_structures/?utm_source=chatgpt.com "Flow Control - Helm"
[2]: https://stackoverflow.com/questions/63853679/helm-templating-doesnt-let-me-use-dash-in-names?utm_source=chatgpt.com "Helm templating doesn't let me use dash in names - Stack Overflow"
[3]: https://github.com/helm/helm/issues/2192?utm_source=chatgpt.com "Accessing values of the subchart with dash in the name · Issue #2192"
[4]: https://helm.sh/docs/chart_template_guide/function_list/?utm_source=chatgpt.com "Template Function List - Helm"
[5]: https://github.com/helm/helm/issues/3854?utm_source=chatgpt.com "toYaml's and consistent indentation - ehh... · Issue #3854 · helm/helm"
[6]: https://stackoverflow.com/questions/68618761/helm-chart-volumes-and-volumemounts-in-deployment-file?utm_source=chatgpt.com "Helm chart volumes and volumeMounts in deployment file"
[7]: https://stackoverflow.com/questions/73611461/conditionally-including-part-of-template?utm_source=chatgpt.com "kubernetes helm - conditionally including part of template"
[8]: https://helm.sh/docs/howto/charts_tips_and_tricks/?utm_source=chatgpt.com "Chart Development Tips and Tricks - Helm"
[9]: https://kodekloud.com/blog/helm-flow-control-and-conditionals/?utm_source=chatgpt.com "Helm Flow Control with Conditional Control Structures - KodeKloud"
[10]: https://gist.github.com/MahdiKarimipour/b12be2dc9a982bd00de5370f8fb21615?utm_source=chatgpt.com "Complete Deployment Helm Chart with with Secret Volumes · GitHub"
[11]: https://medium.com/%40john.shaw.zen/helm-map-a-secret-file-in-pod-fd8cb7bd2739?utm_source=chatgpt.com "helm: map a secret file in pod - Medium"
