## Краткое резюме

Чтобы перевести Kiali c `anonymous`-аутентификации на `openid`, нужно (1) сохранить `Client Secret` IdP в **Google Secret Manager (GSM)**, (2) научить **External Secrets Operator (ESO)** читать этот секрет и создавать в кластере Secret нужного формата, и (3) переключить Kiali на стратегию `openid`, указав `client_id`, `issuer_uri`, `scopes` и т. д. в ConfigMap (или CR Kiali). Всё ниже делается один раз; после обновлений IdP секрет в GSM меняете - ESO сам пересинхронизирует Kubernetes-Secret.

---

## 1. Создаём секрет в Google Secret Manager

```bash
printf '%s' "$CLIENT_SECRET" | \
gcloud secrets create kiali-oidc-secret \
  --data-file=- \
  --replication-policy=automatic \
  --labels managed-by=external-secrets
```

Команда «`gcloud secrets create`» создаёт секрет и сразу загружает первую версию значения ([cloud.google.com][1]).

> **Почему без base64?** В GSM храним строку как есть; ESO при создании Kubernetes-Secret автоматически кодирует её в base64 → попадает в поле `data` как требует API ([external-secrets.io][2], [external-secrets.io][3]).

---

## 2. SecretStore для ESO (GCP provider)

Ниже пример для **Workload Identity** (рекомендуется для GKE); если используете сервис-аккаунт-ключ, поменяйте секцию `auth.*` по \[документации] ([external-secrets.io][4]).

```yaml
apiVersion: external-secrets.io/v1
kind: SecretStore          # или ClusterSecretStore
metadata:
  name: gcp-secrets
  namespace: external-secrets
spec:
  provider:
    gcpsm:
      projectID: <YOUR_GCP_PROJECT_ID>
      auth:
        workloadIdentity:
          clusterName:   <GKE_CLUSTER_NAME>
          clusterLocation: <region|zone>
          serviceAccountRef:
            name: eso-sa   # K8s SA с аннотацией iam.gke.io/gcp-service-account
```

Поле `gcpsm` и подполя аутентификации описаны в официальной справке ESO ([external-secrets.io][4]).

---

## 3. ExternalSecret, создающий Secret *kiali*

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: kiali-oidc
  namespace: kiali          # тот же namespace, где работает Kiali
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: gcp-secrets
    kind: SecretStore
  target:
    name: kiali              # имя итогового k8s-Secret
    creationPolicy: Owner
    template:
      type: Opaque
      labels:
        app: kiali
  data:
    - secretKey: oidc-secret             # ключ внутри k8s-Secret
      remoteRef:
        key: kiali-oidc-secret           # имя в GSM
```

Поле `data/secretKey` задаёт ключ `oidc-secret`, а `remoteRef.key` указывает, какой секрет в GSM читать ([external-secrets.io][3]). В кластере появится Secret ровно в требуемом формате из вашего вопроса.

---

## 4. Проверяем

```bash
kubectl get secret kiali -n kiali -o jsonpath='{.data.oidc-secret}' | base64 -d
```

Если вывод — ваш `Client Secret`, значит связка ESO ↔ GSM работает.

---

## 5. Переключаем Kiali на `openid`

### 5.1 Через Kiali CR (Operator/Helm ≥ 1.24)

```yaml
apiVersion: kiali.io/v1alpha1
kind: Kiali
metadata:
  name: kiali
  namespace: kiali
spec:
  secret_name: kiali              # имя созданного выше Secret
  auth:
    strategy: openid
    openid:
      client_id:        "<Client ID>"
      issuer_uri:       "https://<IdP-well-known-URL>"
      redirect_uri:     "https://kiali.example.com/kiali"
      scopes: ["openid","email","az1prod"]
      username_claim:   "email"
      disable_rbac:     true      # если кластер не интегрирован c IdP
```

Минимальный набор полей `strategy`, `client_id` и `issuer_uri` показан в официальных примерах ([kiali.io][5]). Параметр `secret_name` позволяет указать, что Kiali должен брать `oidc-secret` именно из Secret `kiali` (если вы сменили имя, пропишите своё) ([raw.githubusercontent.com][6]).

### 5.2 Если у вас старый Helm-chart с **ConfigMap**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kiali
  namespace: kiali
data:
  config.yaml: |
    auth:
      strategy: openid
      openid:
        client_id:  "<Client ID>"
        issuer_uri: "https://<IdP-well-known-URL>"
        redirect_uri: "https://kiali.example.com/kiali"
        scopes:
          - openid
          - email
          - az1prod
        username_claim: email
```

ConfigMap и CR содержат одинаковые ключи — выберите ту форму, которую использует ваш способ установки ([github.com][7], [kiali.io][5]).

---

## 6. Перезапускаем Kiali

```bash
kubectl rollout restart deployment kiali -n kiali
```

Kiali подмонтирует Secret (`/kiali-secret/oidc-secret`) и начнёт OIDC-flow.

---

## 7. Полезные советы и типовые ошибки

| Симптом                                    | Причина                                                                        | Решение                                                                      |
| ------------------------------------------ | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| Переходит по кругу «Login» → IdP → «Login» | `redirect_uri` в IdP не совпадает с тем, что указан в Kiali                    | Добавьте URL вида `https://<host>/kiali` в список Redirect URL IdP           |
| `Error fetching OpenID provider metadata`  | самоподписанный сертификат IdP                                                 | Создайте ConfigMap `kiali-cabundle` с `openid-server-ca.crt` ([kiali.io][5]) |
| Хотите управлять секретом «по-взрослому»   | В новых версиях Kiali обсуждается поддержка CSI/ESO напрямую ([github.com][8]) | Пока что используйте описанный выше способ                                   |

---

## 8. Что менять при обновлении Client Secret

* Обновите значение версии в GSM (`gcloud secrets versions add kiali-oidc-secret --data-file=-`).
* Подождите `refreshInterval` ESO (или запустите `kubectl annotate externalsecret kiali-oidc force-sync="$(date +%s)"`).
* Kiali перечитает Secret автоматически — перезапуск не нужен.

---

### Где почитать дальше

* Kiali OpenID docs ([kiali.io][5])
* ESO + GCP provider и Workload Identity ([external-secrets.io][4])
* Пример ExternalSecret c GSM ([external-secrets.io][3])
* Обзор ESO на GKE (Medium) ([medium.com][9])
* Дополнительные шаблоны (dataFrom, типы Secret) ([external-secrets.io][2], [external-secrets.io][10])

[1]: https://cloud.google.com/sdk/gcloud/reference/secrets/create?utm_source=chatgpt.com "gcloud secrets create | Google Cloud SDK Documentation"
[2]: https://external-secrets.io/v0.5.6/guides-common-k8s-secret-types/ "Common K8S Secret Types - External Secrets Operator"
[3]: https://external-secrets.io/v0.5.1/provider-google-secrets-manager/ "Secret Manager - External Secrets Operator"
[4]: https://external-secrets.io/latest/provider/google-secrets-manager/ "Google Cloud Secret Manager - External Secrets Operator"
[5]: https://kiali.io/docs/configuration/authentication/openid/ "OpenID Connect strategy | Kiali"
[6]: https://raw.githubusercontent.com/kiali/kiali-operator/master/crd-docs/crd/kiali.io_kialis.yaml?utm_source=chatgpt.com "here - GitHub"
[7]: https://github.com/kiali/kiali/issues/3042?utm_source=chatgpt.com "Kiali not working with OIDC for 1.19 · Issue #3042 - GitHub"
[8]: https://github.com/kiali/kiali/issues/6942 "Enhancing Kiali OIDC process by supporting CSI secrets · Issue #6942 · kiali/kiali · GitHub"
[9]: https://medium.com/google-cloud/secrets-management-using-external-secret-operator-for-goole-secret-manager-on-gke-2e20f38a66bf "Secrets Management: Using External Secret Operator on GKE and Google Secret Manager. | by Rakesh Saw | Google Cloud - Community | Medium"
[10]: https://external-secrets.io/latest/guides/all-keys-one-secret/ "Extract structured data - External Secrets Operator"
