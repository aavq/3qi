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

***
***
***

Below is a concise, step-by-step cookbook for working **inside an existing Google Cloud project** where the secret
`ENVOY_CRED_BUNDLE` already exists. You will:

1. Point `gcloud` at the correct project.
2. Add a **new version** from the file `envoy-secrets.json`.
3. Confirm the new version number and inspect its metadata & contents.
4. Copy that version number into your `ExternalSecret` manifest.

---

## 1  Activate the right project

```bash
# one-time login if you have not yet authenticated
gcloud auth login

# make <PROJECT_ID> the active project for all further commands
gcloud config set project <PROJECT_ID>
```

`gcloud config set project` changes the SDK’s active project in the current configuration, which every subsequent command will inherit ([Google Cloud][1], [Stack Overflow][2], [Google Cloud][3]).

To double-check:

```bash
gcloud config list --format='text(core.project)'
```

---

## 2  Add a new secret **version**

Google Secret Manager secrets are *immutable*; you never overwrite a value—you add a version. The CLI syntax is:

```bash
gcloud secrets versions add ENVOY_CRED_BUNDLE \
       --data-file=envoy-secrets.json
```

This command uploads the file verbatim, creates a new version, and prints its fully-qualified name (ending in `/versions/<NUMBER>`). The same syntax is shown in the official docs under “Add a secret version → gcloud” ([Google Cloud][4], [Google Cloud][5], [Google Cloud][6]).

### Capture the version ID automatically (optional)

```bash
NEW_VER=$(gcloud secrets versions add ENVOY_CRED_BUNDLE \
              --data-file=envoy-secrets.json \
              --format='value(name)' | awk -F/ '{print $NF}')
echo "Created version: $NEW_VER"
```

---

## 3  Verify the new version

### 3.1 List all versions

```bash
gcloud secrets versions list ENVOY_CRED_BUNDLE
```

The table shows **NAME**, **STATE**, and **CREATED** for every version; the highest number is the one you just added ([Google Cloud][7], [Google Cloud][8], [GitGuardian Blog][9]).

### 3.2 Describe that specific version

```bash
gcloud secrets versions describe $NEW_VER --secret=ENVOY_CRED_BUNDLE
```

You will see metadata (create time, state, etag, etc.) exactly as in the docs ([Google Cloud][10], [Google Cloud][7]).

### 3.3 (Optionally) view the payload for a smoke-test

```bash
gcloud secrets versions access $NEW_VER --secret=ENVOY_CRED_BUNDLE \
        --format='text' | head
```

Only run this if you are allowed to see secret contents. Guidance on listing and accessing versions is covered in blogs and CLI references ([GitGuardian Blog][9], [Fig][11]).

---

## 4  Reference the version in **ExternalSecret**

If you want to pin to the exact version you just created:

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
    name: envoy-oauth-secrets      # Kubernetes Secret to create
    creationPolicy: Owner
  dataFrom:
  - extract:
      key: ENVOY_CRED_BUNDLE
      version: "«NEW_VER»"         # e.g. "5"
```

*Leaving `version:` blank or using `"latest"` also works if your team is comfortable always taking the most recent version* ([Google Cloud][4]).

---

## 5  Common pitfalls & tips

| Issue                                      | Fix / Note                                                                                                        |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| **Permission denied** on `versions add`    | Ensure your principal has `roles/secretmanager.secretVersionAdder` or higher ([Google Cloud][4])                  |
| `gcloud` still points to the wrong project | Run `gcloud config configurations list` to see active config, then switch or set the project again ([Medium][12]) |
| Version numbers look wrong                 | Remember they are **incremental**, so uploading twice in a row yields `…/2`, `…/3`, etc. ([Google Cloud][7])      |
| Need to script in CI                       | Use `--quiet` to suppress prompts and `--format='value(name)'` to capture the version cleanly ([Fig][13])         |

---

### **Result**

After these steps you will have a fresh version of `ENVOY_CRED_BUNDLE` containing both `hmac.yaml` and `token-secret.yaml`. You verified the upload, obtained its version number, and wired that value into `ExternalSecret`. Kubernetes will now synchronise the secret exactly as intended.

[1]: https://cloud.google.com/sdk/gcloud/reference/config/set?utm_source=chatgpt.com "gcloud config set | Google Cloud CLI Documentation"
[2]: https://stackoverflow.com/questions/46770900/how-to-change-the-project-in-gcp-using-cli-commands?utm_source=chatgpt.com "How to change the project in GCP using CLI commands"
[3]: https://cloud.google.com/sdk/docs/configurations?utm_source=chatgpt.com "Managing gcloud CLI configurations"
[4]: https://cloud.google.com/secret-manager/docs/add-secret-version "Add a secret version  |  Secret Manager Documentation  |  Google Cloud"
[5]: https://cloud.google.com/sdk/gcloud/reference/secrets/versions/add?utm_source=chatgpt.com "gcloud secrets versions add | Google Cloud CLI Documentation"
[6]: https://cloud.google.com/secret-manager/docs/add-secret-version?utm_source=chatgpt.com "Add a secret version | Secret Manager Documentation - Google Cloud"
[7]: https://cloud.google.com/secret-manager/docs/view-secret-version?utm_source=chatgpt.com "View secret version details | Secret Manager Documentation"
[8]: https://cloud.google.com/secret-manager/docs/samples/secretmanager-list-secret-versions?utm_source=chatgpt.com "List secret versions | Secret Manager Documentation - Google Cloud"
[9]: https://blog.gitguardian.com/how-to-handle-secrets-with-google-cloud-secret-manager/?utm_source=chatgpt.com "How to Handle Secrets with Google Cloud Secret Manager"
[10]: https://cloud.google.com/sdk/gcloud/reference/secrets/versions/describe?utm_source=chatgpt.com "gcloud secrets versions describe | Google Cloud CLI Documentation"
[11]: https://fig.io/manual/gcloud/secrets/versions/add?utm_source=chatgpt.com "gcloud secrets versions add <SECRET> - Fig.io"
[12]: https://medium.com/google-cloud/setup-and-switch-between-google-cloud-projects-in-the-sdk-885c5000624c?utm_source=chatgpt.com "Setup and Switch Between Google Cloud Projects in the SDK"
[13]: https://fig.io/manual/gcloud/secrets/describe?utm_source=chatgpt.com "gcloud secrets describe <SECRET> - Fig.io"


***
***
***


### Кратко

Ниже показано, как в действующем проекте Google Cloud: (1) переключиться на нужный ID проекта, (2) загрузить новую версию уже существующего секрета `ENVOY_CRED_BUNDLE` из файла `envoy-secrets.json`, (3) убедиться, что версия создана, и (4) сослаться на номер версии в манифесте `ExternalSecret`.

---

## 1  Настраиваем `gcloud` на нужный проект

```bash
gcloud auth login           # при необходимости
gcloud config set project <PROJECT_ID>
```

Команда `gcloud config set project` изменяет «активный» проект в текущей конфигурации CLI — все последующие вызовы будут работать именно с ним ([cloud.google.com][1]).
Проверить:

```bash
gcloud config list --format='text(core.project)'
```

---

## 2  Добавляем новую версию секрета

```bash
gcloud secrets versions add ENVOY_CRED_BUNDLE \
       --data-file=envoy-secrets.json
```

`Secret Manager` никогда не перезаписывает данные; вместо этого создаётся новая версия, а предыдущие остаются доступными ([cloud.google.com][2], [cloud.google.com][3]).
CLI выводит полный ресурсный путь вида
`projects/<PROJECT_ID>/secrets/ENVOY_CRED_BUNDLE/versions/<NUM>` — последний компонент и есть номер версии.

### Автоматически сохранить номер версии

```bash
NEW_VER=$(gcloud secrets versions add ENVOY_CRED_BUNDLE \
            --data-file=envoy-secrets.json \
            --format='value(name)' | awk -F/ '{print $NF}')
echo "Создана версия: $NEW_VER"
```

`--format='value(name)'` оставляет только поле `name`, а `awk` выделяет числовой хвост ([cloud.google.com][3]).

---

## 3  Проверяем созданную версию

| Цель                                        | Команда                                                                  |        |
| ------------------------------------------- | ------------------------------------------------------------------------ | ------ |
| **Список всех версий**                      | `gcloud secrets versions list ENVOY_CRED_BUNDLE`                         |        |
| **Метаданные конкретной версии**            | `gcloud secrets versions describe $NEW_VER --secret=ENVOY_CRED_BUNDLE`   |        |
| **Просмотр содержимого (при наличии прав)** | \`gcloud secrets versions access \$NEW\_VER --secret=ENVOY\_CRED\_BUNDLE | head\` |

Эти команды опираются на стандартные подкоманды CLI `list`, `describe`, `access`, описанные в официальной документации ([cloud.google.com][4], [cloud.google.com][5], [cloud.google.com][6]).

---

## 4  Указываем версию в `ExternalSecret`

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
  dataFrom:
  - extract:
      key: ENVOY_CRED_BUNDLE
      version: "{{NEW_VER}}"     # например "5"
```

* Если хотите всегда получать самую свежую версию, используйте `version: "latest"` (опция поддерживается тем же API) ([cloud.google.com][2]).

---

## 5  Частые проблемы и решения

| Симптом                                   | Решение                                                                                                                                                               |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **PERMISSION\_DENIED** при `versions add` | Убедитесь, что ваша учётная запись или сервис-аккаунт имеет роль `roles/secretmanager.secretVersionAdder` или выше ([cloud.google.com][2])                            |
| `gcloud` обращается к чужому проекту      | Запустите `gcloud config list`, чтобы убедиться в корректности поля `core.project`, или переключитесь через `gcloud config set project` снова ([cloud.google.com][7]) |
| Непонятно, какую версию указать           | Используйте команду из шага 2 для автоматического сохранения номера; версии нумеруются последовательно (1, 2, 3…) ([cloud.google.com][4])                             |

---

**Результат:** новая версия секрета `ENVOY_CRED_BUNDLE` загружена из `envoy-secrets.json`, её номер известен и прописан в `ExternalSecret`, благодаря чему ESO синхронизирует свежие данные в Kubernetes-Secret без вмешательства вручную.

[1]: https://cloud.google.com/sdk/gcloud "gcloud CLI overview | Google Cloud CLI Documentation"
[2]: https://cloud.google.com/secret-manager/docs/add-secret-version "Add a secret version | Secret Manager Documentation - Google Cloud"
[3]: https://cloud.google.com/sdk/gcloud/reference/secrets/versions/add "gcloud secrets versions add | Google Cloud CLI Documentation"
[4]: https://cloud.google.com/sdk/gcloud/reference/secrets/versions/list "gcloud secrets versions list | Google Cloud CLI Documentation"
[5]: https://cloud.google.com/secret-manager/docs/view-secret-version "View secret version details | Secret Manager Documentation"
[6]: https://cloud.google.com/secret-manager/docs/samples/secretmanager-list-secret-versions "List secret versions | Secret Manager Documentation - Google Cloud"
[7]: https://cloud.google.com/sdk/docs/configurations "Managing gcloud CLI configurations"


