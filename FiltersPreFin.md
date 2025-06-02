Попробуй понять, что выполняется в этой инструкции, поняв это напиши инструкцию на английском языке, сохранив как можно больше деталей из этой инструкции, по возможности используя лучшие практики написания инструкций: 

Итак, основная мысль:
Есть два способа фильтровать трафик при помощи Envoy фильтра OAuth2:
1. На уровне context SIDECAR_INBOUND
2. На уровне context GATEWAY

В зависимости от выбранного способа, секреты должны быть добавлены либо в namespace в котором запущен Pod c SIDECAR либо в namespace с Istio Ingress Gateway

Добавление OAuth2 Envoy Filter начинается с того что нужно нужно создать секрет, содержащий два yaml файла:
- Client Secret (.yaml)
- HMAC (.yaml)

Пример создания секрета для namespace с Istio Ingress Gateway, но так же нужен подробный пример для namespace в котором запущен Pod c SIDECAR.

Первая чать секрета - HMAC, может быть сгенерирован один раз локально, следующим образом:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
e46f5c2a1f36bcbe27cac7f1fd369494d60e9085d6347dd34f653e919d1a215e
```

Дальше рассмотрим создание Secret для контекста Gateway в namespace с Istio Ingress Gateway. Условимся что имя секрета будет envoy-oauth-secrets

Цель: получить в namespace istio-system Secret с именеи envoy-oauth-secrets, который будет содержать два yaml файла в кодировке base64 - hmac.yaml и token-secret.yaml

Пример файла - секрета:

```yaml
# kubectl -n istio-system get secrets envoy-oauth-secrets -oyaml
apiVersion: v1
kind: Secret
type: Opaque
metadata:
  name: envoy-oauth-secrets
  namespace: istio-system
data:
  hmac.yaml: LS0tCnJlc291cmNlczoKLSAiQHR5cGUiOiB0eXBlLmdvb2dsZWFwaXMuY29tL2Vudm95LmV4dGVuc2lvbnMudHJhbnNwb3J0X3NvY2tldHMudGxzLnYzLlNlY3JldAogIG5hbWU6IGhtYWMKICBnZW5lcmljX3NlY3JldDoKICAgIHNlY3JldDoKICAgICAgaW5saW5lX3N0cmluZzogNzBmZWI5MzM0ZmI3NmEzNGMwOGI0NzBiNmM4NDhjOGFmNDYwMGZlZDExZjI0YjBmZWQ0MzM2ZjI3MzYzZTA5YgoK
  token-secret.yaml: LS0tCnJlc291cmNlczoKLSAiQHR5cGUiOiB0eXBlLmdvb2dsZWFwaXMuY29tL2Vudm95LmV4dGVuc2lvbnMudHJhbnNwb3J0X3NvY2tldHMudGxzLnYzLlNlY3JldAogIG5hbWU6IHRva2VuCiAgZ2VuZXJpY19zZWNyZXQ6CiAgICBzZWNyZXQ6CiAgICAgIGlubGluZV9zdHJpbmc6IDFCaW1uWksxR2xRMDhVRlY5eGlTbEtxVkhEUVUydnZOCgo=
```


Для этого создадим файлы-секретов в фармате Envoy Secret discovery service (SDS)


2. Создать yaml-файл с именем hmac.yaml и содержимым в формате envoy Secret:

```yaml
---
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: hmac
  generic_secret:
    secret:
      inline_string: 70feb9334fb76a34c08b470b6c848c8af4600fed11f24b0fed4336f27363e09b
```

3. Так же создать yaml-файл с именем token-secret.yaml и содержимым в формате envoy Secret:
```yaml
---
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: token
  generic_secret:
    secret:
      inline_string: 1BimnZK1GlQ08UFV9xiSlKqVHDQU2vvN
```


Это может быть выполнено вот так:

```bash
cat > hmac.yaml <<'EOF'
---
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: hmac
  generic_secret:
    secret:
      inline_string: 70feb9334fb76a34c08b470b6c848c8af4600fed11f24b0fed4336f27363e09b
EOF
```

```bash
cat > token-secret.yaml <<'EOF'
---
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: token
  generic_secret:
    secret:
      inline_string: 1BimnZK1GlQ08UFV9xiSlKqVHDQU2vvN
EOF
```


Далее необходимо создать json-файл, содержищий оба этих секрета, Это может быть выполнено вот так:


```bash
jq -n --rawfile h hmac.yaml --rawfile t token-secret.yaml '{ "hmac.yaml": $h, "token-secret.yaml": $t }' > oauth-secrets.json
```

Проверяем что формат созданных фанных в json не изменился

```bash
jq -r '.["hmac.yaml"]' oauth-secrets.json |yq
jq -r '.["token-secret.yaml"]' oauth-secrets.json |yq
```


Можно валидировать секреты вот так (опционально, только при наличии istioctl):

```bash
jq -r '.["hmac.yaml"]' oauth-secrets.json | \
istioctl validate -f -
validation succeed
```

Теперь секрет-файл в json формате готов для добавления новой версии секрета в GSM, в GCP.

Если логин ещё не сделан, то выполним:

```bash
gcloud auth login
```

После этого установим в качестве текущего проекта, тот проект в котором нужно создать новую версию секрета:

```bash
gcloud config set project <PROJECT_ID>
```


Убедимся что проект установлен кактекущий:

```bash
gcloud config list --format='text(core.project)'
# project: <PROJECT_ID>
```

Так же, нужно убедиться что секрет, версию которого мы хотим обновить уже существует

```bash
gcloud secrets list --filter=<SECTER_NAME>
```

Проверим, какие есть версии этого секрета:

```bash
gcloud secrets versions list <SECTER_NAME>
```

Добавим новую версию:

```bash
gcloud secrets versions add <SECTER_NAME> \
       --data-file=oauth-secrets.json
```

Проверим что версия была добавлена:

```bash
gcloud secrets versions list <SECTER_NAME>
```

```yaml
---
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
      version: "{{NEW_VER}}"
```

***
***
***

3. Необходимо весь секрет секрет смонтировать в каталог  `/etc/istio/creds`
Для этого отредактируем template в Deployment Ingress Gateway

```yaml
apiVersion: apps/v1
kind: Deployment
...
spec:
  template:
    spec:
      volumes:
      - name: envoy-creds
        secret:
          secretName: envoy-oauth-secrets
          defaultMode: 0440
      containers:
      - name: istio-proxy
        image: ...
        volumeMounts:
        - name: envoy-creds
          mountPath: /etc/istio/creds       # 2 files:
                                            # /etc/istio/creds/hmac.yaml
                                            # /etc/istio/creds/token-secret.yaml
          readOnly: true
```

Таким образам в Pod в каталоге `/etc/istio/creds` будет создано два файла:
  ├── `token-secret.yaml`
  └── `hmac.yaml`

Пример:

```yaml
      volumes:
        - name: oauth-secrets
          secret:
            defaultMode: 420
            secretName: envoy-oauth-secrets

          volumeMounts:
            - mountPath: /etc/istio/creds
              name: oauth-secrets
              readOnly: true
```

В случае с context: SIDECAR_INBOUND, файлы-секреты могут быть примонтированы через annotations так же в Deployment но уже не Ingress Gateway, а в template Deployment приложения, которому добавляется sidecar

```yaml
  template:
    metadata:
      annotations:
        sidecar.istio.io/userVolume: |
          [{
          "name": "oauth-secrets",
          "secret": {
              "secretName": "envoy-oauth-secrets"
          }
          }]
        sidecar.istio.io/userVolumeMount: |
          [{
          "name": "oauth-secrets",
          "mountPath": "/etc/istio/creds",
          "readOnly": true
          }]

```


4. Всё готово для добавления фильтра с контекстом GATEWAY:

```yaml
# context: GATEWAY
---
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: httpbin-oauth-gw
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
          sni: "httpbin.lima"
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
            authorization_endpoint: https://idp.lima/realms/demo/protocol/openid-connect/auth
            token_endpoint:
              cluster: idp-oauth-cluster
              uri: https://idp.lima/realms/demo/protocol/openid-connect/token
              timeout: 5s
            redirect_uri: "%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback"
            redirect_path_matcher:
              path: { exact: /callback }
            signout_path:
              path: { exact: /logout }
            credentials:
              client_id: my-test-app
              token_secret:
                name: token
                sds_config: { path: /etc/istio/creds/token-secret.yaml }
              hmac_secret:
                name: hmac
                sds_config: { path: /etc/istio/creds/hmac.yaml }
              cookie_domain: ".lima"
              cookie_names:
                bearer_token: BearerToken
                oauth_expires: OauthExpires
            auth_scopes: ["openid", "profile", "email"]
            forward_bearer_token: true
            use_refresh_token: true

  - applyTo: CLUSTER
    patch:
      operation: ADD
      value:
        name: idp-oauth-cluster
        type: LOGICAL_DNS
        lb_policy: ROUND_ROBIN
        connect_timeout: 10s
        load_assignment:
          cluster_name: idp-oauth-cluster
          endpoints:
          - lb_endpoints:
            - endpoint:
                address:
                  socket_address:
                    address: idp.lima
                    port_value: 443
        dns_lookup_family: V4_ONLY
        transport_socket:
          name: envoy.transport_sockets.tls
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
            sni: idp.lima
```

5. А если создавать секрет в namespace приложения, то фильтр можно добавить в namespace приложения и тогда контекст фильтра будет SIDECAR_INBOUND

```yaml
# context: SIDECAR_INBOUND
---
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: httpbin-oauth
  namespace: default
spec:
  priority: 10
  workloadSelector:
    labels:
      app: httpbin
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: SIDECAR_INBOUND
      listener:
        filterChain:
          filter:
            name: envoy.filters.network.http_connection_manager
            subFilter:
                name: envoy.filters.http.router
    patch:
      operation: INSERT_FIRST # INSERT_BEFORE
      value:
        name: envoy.filters.http.oauth2
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
          config:
            pass_through_matcher:
            - name: ":path"
              prefix_match: "/healthz/ready"
            - name: "authorization"
              prefix_match: "Bearer"
            authorization_endpoint: https://idp.lima/realms/demo/protocol/openid-connect/auth
            token_endpoint:
              cluster: idp-oauth-cluster
              uri: https://idp.lima/realms/demo/protocol/openid-connect/token
              timeout: 5s
            redirect_uri: "%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback"
            redirect_path_matcher:
              path: { exact: /callback }
            signout_path:
              path: { exact: /logout }
            credentials:
              client_id: my-test-app
              token_secret:
                name: token
                sds_config: { path: /etc/istio/creds/token-secret.yaml }
              hmac_secret:
                name: hmac
                sds_config: { path: /etc/istio/creds/hmac.yaml }
              cookie_domain: ".lima"
              cookie_names:
                bearer_token: BearerToken
                oauth_expires: OauthExpires
            auth_scopes: ["openid", "profile", "email"]
            forward_bearer_token: true
            use_refresh_token: true

  - applyTo: CLUSTER
    patch:
      operation: ADD
      value:
        name: idp-oauth-cluster
        type: LOGICAL_DNS
        lb_policy: ROUND_ROBIN
        connect_timeout: 10s
        load_assignment:
          cluster_name: idp-oauth-cluster
          endpoints:
          - lb_endpoints:
            - endpoint:
                address:
                  socket_address:
                    address: idp.lima
                    port_value: 443
        dns_lookup_family: V4_ONLY
        transport_socket:
          name: envoy.transport_sockets.tls
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
            sni: idp.lima
```



FOO:

```bash
NEW_VER=$(gcloud secrets versions add ENVOY_CRED_BUNDLE \
              --data-file=envoy-secrets.json \
              --format='value(name)' | awk -F/ '{print $NF}')
echo "Created version: $NEW_VER"
```


```bash
# CHECK IT
gcloud secrets versions describe $NEW_VER --secret=ENVOY_CRED_BUNDLE

gcloud secrets versions access $NEW_VER --secret=ENVOY_CRED_BUNDLE \
        --format='text' | head
```


```yaml
---
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
    name: envoy-oauth-secrets # Kubernetes Secret to create
    creationPolicy: Owner
  dataFrom:
  - extract:
      key: ENVOY_CRED_BUNDLE
```



```yaml
# context: SIDECAR_INBOUND
---
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: httpbin-oauth
  namespace: default
spec:
  priority: 10
  workloadSelector:
    labels:
      app: httpbin
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: SIDECAR_INBOUND
      listener:
        filterChain:
          filter:
            name: envoy.filters.network.http_connection_manager
            subFilter:
                name: envoy.filters.http.router
    patch:
      operation: INSERT_FIRST # INSERT_BEFORE
      value:
        name: envoy.filters.http.oauth2
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
          config:
            pass_through_matcher:
            - name: ":path"
              prefix_match: "/healthz/ready"
            - name: "authorization"
              prefix_match: "Bearer"
            authorization_endpoint: https://idp.lima/realms/demo/protocol/openid-connect/auth
            token_endpoint:
              cluster: idp-oauth-cluster
              uri: https://idp.lima/realms/demo/protocol/openid-connect/token
              timeout: 5s
            redirect_uri: "%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback"
            redirect_path_matcher:
              path: { exact: /callback }
            signout_path:
              path: { exact: /logout }
            credentials:
              client_id: my-test-app
              token_secret:
                name: token
                sds_config: { path: /etc/istio/creds/token-secret.yaml }
              hmac_secret:
                name: hmac
                sds_config: { path: /etc/istio/creds/hmac.yaml }
              cookie_domain: ".lima"
              cookie_names:
                bearer_token: BearerToken
                oauth_expires: OauthExpires
            auth_scopes: ["openid", "profile", "email"]
            forward_bearer_token: true
            use_refresh_token: true

  - applyTo: CLUSTER
    patch:
      operation: ADD
      value:
        name: idp-oauth-cluster
        type: LOGICAL_DNS
        lb_policy: ROUND_ROBIN
        connect_timeout: 10s
        load_assignment:
          cluster_name: idp-oauth-cluster
          endpoints:
          - lb_endpoints:
            - endpoint:
                address:
                  socket_address:
                    address: idp.lima
                    port_value: 443
        dns_lookup_family: V4_ONLY
        transport_socket:
          name: envoy.transport_sockets.tls
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
            sni: idp.lima
```


