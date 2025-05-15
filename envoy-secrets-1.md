Ниже — рабочий рецепт, как упаковать **два YAML-файла** в один JSON-секрет Google Secret Manager (GSM) и устранить ошибку `Invalid numeric literal`. Суть в том, что вместо `--slurpfile`, который пытается разобрать вход как JSON, нужно использовать `--rawfile`, читающий содержимое файла «как есть». ([jqlang.org][1], [Stack Overflow][2])

## Почему падает `--slurpfile`

* `--slurpfile` читает файл как **массив JSON-документов**; YAML к этому моменту ещё не JSON, поэтому парсер останавливается на первом символе (`-`) и бросает «Invalid numeric literal». ([jqlang.org][1], [GitHub][3])
* Нам нужно поместить содержимое файлов **сырым текстом** в поля JSON, а не парсить его. Для этого и существует `--rawfile`. ([jqlang.org][1], [docs.rackn.io][4])

## Правильная команда `jq`

```bash
jq -n \
  --rawfile h hmac.yaml \
  --rawfile t token-secret.yaml \
  '{ "hmac.yaml": $h, "token-secret.yaml": $t }' \
  > envoy-secrets.json
```

* `-n` — старт без входного потока;
* `--rawfile var file` — кладёт **полное содержимое** `file` в переменную `$var` строкой;
* в результирующем объекте ключи совпадают с будущими именами файлов-ключей K8s-секрета.

Проверьте результат локально (расшифровка длинных строк не нужна, это уже готовый YAML):

```bash
jq -r '.["hmac.yaml"]' envoy-secrets.json | head
```

## Загрузка секрета в Google Secret Manager

```bash
gcloud secrets create envoy-cred-bundle \
  --replication-policy=automatic \
  --data-file=envoy-secrets.json
```

Команда создаст секрет с одной версией, содержащей весь JSON-объект; лимит GSM — 64 KiB на версию, что значительно больше ваших двух файлов. ([Google Cloud][5], [Google Cloud][6])

> Если секрет уже существует, используйте
> `gcloud secrets versions add envoy-cred-bundle --data-file=envoy-secrets.json`

## ExternalSecret (один секрет → несколько ключей)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: envoy-oauth-secrets
  namespace: istio-system
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: gsm-store
    kind: SecretStore
  target:
    name: envoy-oauth-secrets
    creationPolicy: Owner
    template:
      type: Opaque
  dataFrom:
  - extract:
      key: envoy-cred-bundle    # JSON из GSM
```

Поле `extract` разворачивает каждую пару «ключ-значение» из JSON в отдельный ключ Kubernetes-Secret. ([External Secrets][7], [External Secrets][8])

## Монтирование в Pod

Оставьте `items:` пустым — Kubernetes автоматически создаст файлы с именами ключей (`hmac.yaml`, `token-secret.yaml`) в указанной директории:

```yaml
volumes:
- name: envoy-creds
  secret:
    secretName: envoy-oauth-secrets
...
volumeMounts:
- name: envoy-creds
  mountPath: /etc/istio/creds   # /etc/istio/creds/hmac.yaml, /etc/istio/creds/token-secret.yaml
  readOnly: true
```

Kubernetes допускает точки в именах ключей и при монтировании использует их как имена файлов. ([Kubernetes][9], [Kubernetes][10])

## Проверка

1. **Содержимое секрета**

   ```bash
   kubectl -n istio-system get secret envoy-oauth-secrets -o jsonpath='{.data["hmac.yaml"]}' | base64 -d | head
   ```
2. **Наличие файлов в Pod**

   ```bash
   kubectl exec <pod> -c istio-proxy -- ls /etc/istio/creds
   ```

Если видите оба файла и их YAML-контент совпадает с ожиданием — задача решена.

---

### Что запомнить

| Шаг                      | Ключевая команда/факт                                            |
| ------------------------ | ---------------------------------------------------------------- |
| Сборка JSON              | `jq --rawfile` вместо `--slurpfile` ([Stack Overflow][2])        |
| Лимит GSM                | 64 KiB на версию ([Google Cloud][6])                             |
| Разворачивание ключей    | `dataFrom.extract` в ExternalSecret ([External Secrets][7])      |
| Монтирование всех ключей | omit `items:` → каждый ключ становится файлом ([Kubernetes][10]) |

Теперь оба Envoy-YAML-секрета живут в одном секрете GSM, корректно синхронизируются в Kubernetes и доступны приложению именно в том виде, который ему нужен.

[1]: https://jqlang.org/manual/?utm_source=chatgpt.com "jq 1.7 Manual"
[2]: https://stackoverflow.com/questions/60418971/import-plain-text-file-in-to-json-via-jq?utm_source=chatgpt.com "Import plain text file in to JSON via JQ - Stack Overflow"
[3]: https://github.com/stedolan/jq/issues/2415?utm_source=chatgpt.com "No way to slurp multiple raw inputs without joining them · Issue #2415"
[4]: https://docs.rackn.io/dev/developers/cli/jq/?utm_source=chatgpt.com "JQ Usage Examples - Documentation"
[5]: https://cloud.google.com/secret-manager/docs/creating-and-accessing-secrets?utm_source=chatgpt.com "Create a secret | Secret Manager Documentation - Google Cloud"
[6]: https://cloud.google.com/secret-manager/quotas?utm_source=chatgpt.com "Quotas and limits | Secret Manager Documentation - Google Cloud"
[7]: https://external-secrets.io/latest/guides/all-keys-one-secret/?utm_source=chatgpt.com "Extract structured data - External Secrets Operator"
[8]: https://external-secrets.io/v0.8.1/api/spec/?utm_source=chatgpt.com "API specification - External Secrets Operator"
[9]: https://kubernetes.io/docs/concepts/configuration/secret/?utm_source=chatgpt.com "Secrets | Kubernetes"
[10]: https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/?utm_source=chatgpt.com "Distribute Credentials Securely Using Secrets - Kubernetes"
