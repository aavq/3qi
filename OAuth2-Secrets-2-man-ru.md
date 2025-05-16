**Кратко — как безопасно и воспроизводимо подключить встроенный фильтр Envoy *oauth2* к Istio**

1. **Определитесь, где проводить аутентификацию** — на шлюзе Ingress (*context: GATEWAY*) или в боковом прокси приложения (*context: SIDECAR\_INBOUND*).
2. **Сгенерируйте два секрета — `token` и `hmac` — в формате Envoy SDS.**
3. **Упакуйте оба YAML-фрагмента в один JSON-файл и загрузите новой версией секрета в Google Cloud Secret Manager (GSM).**
4. **Протяните секрет в Kubernetes через External Secrets Operator (ESO).**
5. **Смонтируйте полученный Secret в Pods — либо у ingress-gateway, либо в приложениях (через аннотации `sidecar.istio.io/*`).**
6. **Добавьте `EnvoyFilter`, вставляющий HTTP-фильтр OAuth2 в нужном контексте.**

Ниже пошагово раскрываются все этапы, включая команды проверки и рекомендации для продакшена.

---

## 1. Выберите контекст применения

| Контекст             | Когда использовать                                          | Где должен находиться Kubernetes Secret            |
| -------------------- | ----------------------------------------------------------- | -------------------------------------------------- |
| **GATEWAY**          | Единая точка входа; общая авторизация для всех сервисов     | Пространство `istio-system` (Pods ingress-gateway) |
| **SIDECAR\_INBOUND** | Точечная авторизация для конкретного сервиса или неймспейса | Неймспейс самого приложения                        |

---

## 2. Создайте секреты в формате SDS

### 2.1 Генерация значений

```bash
python3 - <<'PY'
import secrets; print(secrets.token_hex(32))
PY
```

Выполните команду дважды: первый вывод пойдёт в `hmac.yaml`, второй — в `token-secret.yaml`.

### 2.2 YAML для `hmac.yaml`

```yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: hmac
  generic_secret:
    secret:
      inline_string: <HEX_СТРОКА_HMAC>
```

### 2.3 YAML для `token-secret.yaml`

```yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: token
  generic_secret:
    secret:
      inline_string: <HEX_СТРОКА_TOKEN>
```

### 2.4 Объедините два файла в JSON

```bash
jq -n --rawfile h hmac.yaml --rawfile t token-secret.yaml \
   '{ "hmac.yaml": $h, "token-secret.yaml": $t }' > oauth-secrets.json
```

---

## 3. Загрузите или обновите секрет в GSM

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>

gcloud secrets versions add ENVOY_CRED_BUNDLE \
     --data-file=oauth-secrets.json
```

---

## 4. Синхронизация секрета в Kubernetes через ESO

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: envoy-oauth-secrets
  namespace: istio-system          # или неймспейс приложения
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: gsm-store
    kind: SecretStore
  target:
    name: envoy-oauth-secrets      # имя создаваемого K8s Secret
    creationPolicy: Owner
  dataFrom:
  - extract:
      key: ENVOY_CRED_BUNDLE       # имя секрета в GSM
```

---

## 5. Монтирование секрета в Envoy

### 5.1 В Deployment ingress-gateway

```yaml
volumes:
- name: envoy-creds
  secret:
    secretName: envoy-oauth-secrets
    defaultMode: 0440
containers:
- name: istio-proxy
  volumeMounts:
  - name: envoy-creds
    mountPath: /etc/istio/creds     # hmac.yaml и token-secret.yaml
    readOnly: true
```

### 5.2 Через аннотации в пользовательских Pods

```yaml
metadata:
  annotations:
    sidecar.istio.io/userVolume: |
      [{"name":"oauth-secrets","secret":{"secretName":"envoy-oauth-secrets"}}]
    sidecar.istio.io/userVolumeMount: |
      [{"name":"oauth-secrets","mountPath":"/etc/istio/creds","readOnly":true}]
```

---

## 6. Добавление фильтра OAuth2

### 6.1 Вариант для GATEWAY (упрощённый)

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: oauth2-gateway
  namespace: istio-system
spec:
  priority: 10
  workloadSelector:
    labels:
      istio: ingressgateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
      listener:
        portNumber: 8443
        filterChain:
          filter:
            name: envoy.filters.network.http_connection_manager
            subFilter:
              name: envoy.filters.http.router
    patch:
      operation: INSERT_FIRST
      value:
        name: envoy.filters.http.oauth2
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
          config:
            authorization_endpoint: https://idp.example/auth
            token_endpoint:
              cluster: idp-oauth
              uri: https://idp.example/token
              timeout: 5s
            redirect_uri: "%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback"
            credentials:
              client_id: demo-app
              token_secret:
                name: token
                sds_config: { path: /etc/istio/creds/token-secret.yaml }
              hmac_secret:
                name: hmac
                sds_config: { path: /etc/istio/creds/hmac.yaml }
            auth_scopes: ["openid","profile","email"]
            forward_bearer_token: true
            use_refresh_token: true
```

Для *SIDECAR\_INBOUND* меняются только `context` и `workloadSelector`.

---

## 7. Чек-лист валидации

| Проверка                | Команда                                          |                                   |
| ----------------------- | ------------------------------------------------ | --------------------------------- |
| Синтаксис YAML-секретов | `istioctl validate -f hmac.yaml`                 |                                   |
| ESO создал Secret       | `kubectl get secret envoy-oauth-secrets -n <ns>` |                                   |
| Envoy видит секреты     | \`pilot-agent request GET config\_dump …         | jq '.static\_resources.secrets'\` |
| Фильтр вставлен         | `istioctl proxy-config listener <pod> -n <ns>`   |                                   |

---

## 8. Лучшие практики для продакшена

* **CSRF-защита** — добавьте HTTP-фильтр CSRF рядом с OAuth2.
* **Исключения для health-checks** — используйте `pass_through_matcher` для `/healthz/*` и Bearer-токенов.
* **Ротация секретов** — публикуйте новую версию в GSM и обновляйте `ExternalSecret` через поле `version`; Envoy подберёт файлы без рестартов.
* **Минимальные IAM-права** — сервис-аккаунту ESO достаточно роли `roles/secretmanager.secretAccessor`.
* **Изоляция неймспейсов** — gateway-секреты держите в `istio-system`, а для sidecar-сервисов — в их собственных неймспейсах.
* **Шаблоны Helm/Kustomize** — избавляют от копипаста и упрощают обновления.
* **Следите за релизами** — изменения в фильтре OAuth2 могут требовать правок конфигов.

---

Следуя этим шагам, вы получаете воспроизводимый, ориентированный на IaC процесс — от генерации секретов до живой проверки OAuth2 во всей сетке сервисов.
