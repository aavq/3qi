Отлично, ты дал всю необходимую информацию. Я разберусь:

- Как правильно настроить `redirect_uri` и маршрут `/callback` для OAuth2 в контексте Istio VirtualService.
- Как выбрать между куками и Bearer-токенами в заголовках — когда и как лучше применять каждый способ.
- Что важно при использовании RS256 токенов с OAuth2-фильтром в Istio/Envoy — включая параметры безопасности, кэширования JWKS и использование refresh токенов.

Соберу рекомендации, примеры конфигураций и объяснение, когда применять каждую стратегию.

Дай мне немного времени, и я вернусь с результатом.

# OAuth2 (Keycloak) аутентификация в Istio: настройка EnvoyFilter, redirect_uri и хранение токена

## Проверка текущей конфигурации EnvoyFilter OAuth2

Чтобы защитить маршрут `https://httpbin.lima` с помощью Keycloak (OIDC/OAuth2), обычно используется **EnvoyFilter** на входном шлюзе Istio. Такой фильтр выполняет перенаправление неаутентифицированных пользователей на Keycloak и последующую обработку токенов. Ниже приведён типовой пример конфигурации EnvoyFilter для OAuth2 (OIDC) с Keycloak:

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: oauth2-ingress
  namespace: istio-system
spec:
  workloadSelector:
    labels:
      istio: ingressgateway              # применяем к ingress-gateway
  configPatches:
  # 1) Добавляем OAuth2-фильтр Envoy перед JWT-фильтром
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
      listener:
        filterChain:
          filter:
            name: envoy.filters.network.http_connection_manager
          subFilter:
            name: envoy.filters.http.jwt_authn
    patch:
      operation: INSERT_BEFORE
      value:
        name: envoy.filters.http.oauth2
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3alpha.OAuth2
          config:
            authorization_endpoint: https://keycloak.local/auth/realms/TEST/protocol/openid-connect/auth
            token_endpoint:
              cluster: oauth                              # имя кластера для обращения к Keycloak
              uri: https://keycloak.local/auth/realms/TEST/protocol/openid-connect/token
              timeout: 3s
            redirect_uri: "%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback"
            redirect_path_matcher:
              path:
                exact: /callback                         # путь для обработки ответа от OAuth2
            credentials:
              client_id: myclient                        # ID клиента Keycloak
              token_secret:
                name: token
                sds_config:
                  path: /etc/istio/config/oauth2/token-secret.yaml   # содержит client_secret
              hmac_secret:
                name: hmac
                sds_config:
                  path: /etc/istio/config/oauth2/hmac-secret.yaml    # случайный секрет для подписи cookie
            auth_scopes: ["openid", "profile", "email"]   # запрашиваемые scope
            use_refresh_token: true                       # (опционально) запрос refresh token
            forward_bearer_token: true                    # передавать токен в заголовке Authorization
            pass_through_matcher:
            - name: authorization
              prefix_match: Bearer                        # пропускать запросы с готовым Bearer токеном
```

**Разбор конфигурации:**

- **authorization_endpoint / token_endpoint** – URL-ы Keycloak для авторизации и обмена кода на токен. В примере указаны для realm `TEST` на хосте `keycloak.local`. 
- **redirect_uri** – URL, на который Keycloak будет перенаправлять пользователя после успешного логина. Использован шаблон `%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback`, чтобы автоматически подставить правильную схему (`http/https`) и хост (домен `httpbin.lima`) из входящего запроса. Path `/callback` выбран в качестве конечной точки возврата. 
- **redirect_path_matcher** – указывает фильтру, что путь `/callback` зарезервирован для обработки ответа от OAuth2. Когда запрос с таким путём приходит, фильтр распознает его как ответ от Keycloak с кодом авторизации.
- **credentials** – настройки OAuth-клиента Keycloak: `client_id` и секрет клиента. Секреты берутся из SDS-конфига (можно хранить Base64-значение client_secret и HMAC-ключа в Kubernetes ConfigMap). Важно убедиться, что client_id и secret соответствуют настройкам клиента в Keycloak.
- **hmac_secret** – секретный ключ для вычисления HMAC. Envoy-фильтр использует его, чтобы подписывать cookies, не позволяя подделать их на стороне клиента.
- **auth_scopes** – списки OIDC scope, запрашиваемых у Keycloak (зависит от того, какие данные нужны; стандартно openid, profile, email).
- **use_refresh_token** – если `true`, фильтр запросит у Keycloak также refresh token (для продления сессии). Для Keycloak это требует scope `offline_access`.
- **forward_bearer_token** – если `true`, после успешной авторизации фильтр будет добавлять полученный Access Token в заголовок `Authorization: Bearer ...` при отправке запроса в сервис, а также устанавливать cookie `BearerToken` для клиента ([OAuth2 — envoy 1.35.0-dev-1e896b documentation](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/oauth2_filter#:~:text=When%20the%20authn%20server%20validates,populated%20with%20the%20same%20value)). В конфигурации выше `forward_bearer_token: true` (это желательно, см. раздел о способе передачи токена).
- **pass_through_matcher** – позволяет пропускать запросы, которые уже содержат заголовок Authorization с Bearer-токеном. Например, если клиент (пользовательский агент или скрипт) уже имеет JWT токен, он может передать его напрямую – Envoy-фильтр обнаружит заголовок и *не будет перенаправлять* на Keycloak. В примере настроено пропускать Authorization, начинающийся с `Bearer` (т.е. любые Bearer JWT). Это удобно для объединения сценариев: интерактивные пользователи проходят через редирект/куки, а сервисы или SPA могут использовать Bearer-токен напрямую.

**Совместимость с RS256 (подпись токенов):** Keycloak по умолчанию подписывает JWT-токены алгоритмом RS256 (асимметричная RSA подпись). Данный подход полностью поддерживается: Envoy-фильтр **не проверяет подпись сам**, а лишь получает токен от IdP. Проверку JWT выполняет Istio через JWT-фильтр (*envoy.filters.http.jwt_authn*), сконфигурированный в Istio **RequestAuthentication**. Нужно убедиться, что в RequestAuthentication указан **issuer** вашего Keycloak realm и **JWKS URI** – URL для получения публичных RSA-ключей Keycloak. Например:

```yaml
apiVersion: security.istio.io/v1beta1
kind: RequestAuthentication
metadata:
  name: jwt-auth
  namespace: istio-system   # можно в istio-system для глобального действия
spec:
  selector:
    matchLabels:
      istio: ingressgateway  # применяем к ingress-gateway (или app: httpbin, если проверять уже на уровне приложения)
  jwtRules:
  - issuer: "https://keycloak.local/auth/realms/TEST"
    jwksUri: "https://keycloak.local/auth/realms/TEST/protocol/openid-connect/certs"
    forwardOriginalToken: true   # чтобы токен не удалялся после проверки (нужно, если upstream сервис читает токен или для AuthorizationPolicy)
    # (при необходимости) fromCookies / fromHeaders можно настроить, см. ниже 
```

Эта конфигурация заставит Istio автоматически валидировать подпись JWT на каждом запросе, сверяя с открытым ключом (JWKS) Keycloak ([envoyfilter.yaml · GitHub](https://gist.github.com/ricosega/a08674756ddbe96cbdbf70e98c063cdc#:~:text=jwtRules%3A%20,test)). При валидном токене Istio пометит запрос как аутентифицированный (доступны поля `request.auth.*` для AuthorizationPolicy). **Важно:** `issuer` и `jwksUri` должны точно соответствовать вашему Keycloak (замените `keycloak.local/TEST` на ваш домен/realm). Алгоритм RS256 будет использован автоматически, т.к. JWKS содержит параметр `alg` для ключа (RSA).

Также может быть настроена **AuthorizationPolicy**, чтобы требовать наличие валидного JWT для доступа к сервису. Например, можно разрешать только запросы с требуемым aud/azp (клиентом) или другими claim, а все остальное – отклонять. Пример (разрешаем только токены клиента `myclient` с aud `myclient`):

```yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: httpbin-authz
  namespace: istio-system
spec:
  selector:
    matchLabels:
      istio: ingressgateway
  rules:
  - when:
    - key: request.auth.presenter   # azp claim
      values: ["myclient"]
    - key: request.auth.audiences   # aud claim
      values: ["myclient"]
```

*(Приведён лишь фрагмент – AuthorizationPolicy можно детализировать по требованиям.)*

**Проверка фильтра:** Убедитесь, что EnvoyFilter применяется корректно. Он должен быть в namespace `istio-system` (если ingressgateway там) и селектор совпадает с метками ingress-шлюза. Также, чтобы фильтр мог вызвать Keycloak, нужен кластер `oauth`. 

> **Важно:** в Envoy **должен существовать cluster** с именем `oauth`, указывающий на хост Keycloak. Если Keycloak – внешний, добавьте либо **ServiceEntry** для его домена, либо включите в EnvoyFilter создание кластера. Например, с помощью второго `configPatch` в EnvoyFilter:
> ```yaml
>  - applyTo: CLUSTER
>    match:
>      cluster:
>        name: "oauth"
>    patch:
>      operation: ADD
>      value:
>        name: "oauth"
>        type: LOGICAL_DNS
>        lb_policy: ROUND_ROBIN
>        connect_timeout: 5s
>        load_assignment:
>          cluster_name: "oauth"
>          endpoints:
>          - lb_endpoints:
>            - endpoint:
>                address:
>                  socket_address:
>                    address: keycloak.local   # адрес Keycloak (DNS или IP)
>                    port_value: 443
>        transport_socket:
>          name: envoy.transport_sockets.tls
>          typed_config:
>            "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
>            sni: keycloak.local
> ```
> Такой блок явно регистрирует кластер `oauth` для обращения на `keycloak.local:443` по TLS ([OAuth2-based authentication on Istio-powered Kubernetes clusters - GetInData](https://getindata.com/blog/OAuth2-based-authentication-on-Istio-powered-Kubernetes-clusters/#:~:text=,value%3A%20name%3A%20oauth%20dns_lookup_family%3A%20V4_ONLY)) ([OAuth2-based authentication on Istio-powered Kubernetes clusters - GetInData](https://getindata.com/blog/OAuth2-based-authentication-on-Istio-powered-Kubernetes-clusters/#:~:text=lb_policy%3A%20ROUND_ROBIN%20transport_socket%3A%20name%3A%20envoy,com%20load_assignment%3A%20cluster_name%3A%20oauth)). (Если Keycloak использует свой сертификат, возможно, понадобится добавить его в траст стор или отключить проверку сертификата на время тестирования.)

После применения EnvoyFilter и настройки JWT-аутентификации можно проверить, что происходит при обращении к `https://httpbin.lima`:

- **Неавторизованный пользователь**: должен быть **перенаправлен** на страницу логина Keycloak. Envoy добавит параметры `client_id`, `redirect_uri` и `scope` к `authorization_endpoint` Keycloak и ответит 302 Redirect.
- **После логина в Keycloak**: браузер перенаправляется на `https://httpbin.lima/callback?code=...&state=...`. Этот запрос приходит опять на ingress, EnvoyFilter распознает путь `/callback` и **перехватывает его**. Фильтр проверит `state`, обменяет код на токен, и при успехе:
  - **Установит cookies** с токеном и метаданными сессии.
  - **Продолжит обработку запроса**, как правило, сразу вернув пользователю **редирект на изначально запрошенный URL** (до логина) ([OAuth2-based authentication on Istio-powered Kubernetes clusters - GetInData](https://getindata.com/blog/OAuth2-based-authentication-on-Istio-powered-Kubernetes-clusters/#:~:text=If%20everything%20succeeds%2C%20you%E2%80%99re%20redirected,forwarded%20to%20the%20downstream%20service)). То есть пользователь автоматически попадает на нужную страницу сервиса, уже будучи аутентифицированным.
  - Envoy OAuth2 фильтр при этом сохранил токен сессии, поэтому повторные запросы не потребуют нового логина.

Из логов или заголовков ответа после `/callback` вы должны увидеть `Set-Cookie: BearerToken=...; Path=/; HttpOnly` (и OauthHMAC, OauthExpires) **при включённом** `forward_bearer_token`. JWT-фильтр Istio проверит токен (подпись RS256 и т.д.) и пропустит запрос к сервису.

Если текущая конфигурация отличается, скорректируйте её по аналогии с приведённым примером. Особенно убедитесь, что **redirect_uri указывает на правильный хост/порт**, а **cluster** для Keycloak настроен. После этого нужно удостовериться, что VirtualService правильно обрабатывает путь `/callback`.

## Настройка redirect_uri и маршрутизации `/callback` в Istio VirtualService

Для успешной OIDC-аутентификации необходимо согласовать настройки на стороне Istio и Keycloak:

- **В Keycloak (клиент):** добавьте в **Valid Redirect URIs** значение `https://httpbin.lima/callback` (или шаблон, допускающий этот путь). Также, если используется `use_refresh_token`, стоит указать **Valid Post Logout Redirect URIs** для `/signout` (если планируется использовать выход).
- **В EnvoyFilter (Istio):** `redirect_uri` уже задан как `.../callback` (как показано выше). Это должно соответствовать ровно тому URI, который разрешён в Keycloak, иначе Keycloak отклонит попытку логина.
- **Istio VirtualService:** необходимо, чтобы запросы на путь `/callback` достигали вашего ingressgateway и обрабатывались EnvoyFilter. Обычно VirtualService для хоста `httpbin.lima` настраивается на проброс всех путей на сервис httpbin. Однако, стоит **явно указать маршрут для `/callback`** во избежание конфликтов с другими правилами. Например:

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: httpbin-vs
  namespace: default
spec:
  hosts:
  - httpbin.lima
  gateways:
  - istio-system/my-gateway          # или используемый ingress-gateway
  http:
  - name: oauth-callback
    match:
    - uri:
        exact: /callback
    route:
    - destination:
        host: httpbin.default.svc.cluster.local
        port:
          number: 8000               # порт сервисa httpbin
    # Возможно, стоит отключить аутентификацию на самом бэкенде для /callback,
    # но EnvoyFilter и так перехватывает /callback до передачи.
  - name: httpbin-main
    match:
    - uri:
        prefix: /
    route:
    - destination:
        host: httpbin.default.svc.cluster.local
        port:
          number: 8000
```

В этом примере VirtualService сначала обрабатывает точный запрос `/callback`, а затем все остальные (`/`). **Почему это нужно:** если у вас были другие правила (например, переписывающие URL или перенаправляющие), важно чтобы `/callback` не модифицировался. Путь `/callback` должен прийти в Envoy **точно так**, как был указан в redirect_uri. В противном случае не сработает валидация `state` и возникнет ошибка “OAuth flow failed” или 404.

Обратите внимание, что **не нужно перенаправлять /callback куда-то еще** – просто маршрутизируйте его к приложению (или оставьте в общий маршрут). EnvoyFilter перехватит этот запрос **до** того, как он дойдет до самого сервиса httpbin, осуществит обмен кода на токен, установит cookies и отправит пользователя дальше. При успешной авторизации Envoy сам вернёт ответ-редирект на исходный путь (через 302 Redirect обратно на запрошенный ранее URL) ([OAuth2-based authentication on Istio-powered Kubernetes clusters - GetInData](https://getindata.com/blog/OAuth2-based-authentication-on-Istio-powered-Kubernetes-clusters/#:~:text=If%20everything%20succeeds%2C%20you%E2%80%99re%20redirected,forwarded%20to%20the%20downstream%20service)). Таким образом, приложение httpbin фактически никогда не увидит путь `/callback` – он обрабатывается на уровне прокси.

Дополнительные рекомендации по настройке **redirect_uri** и безопасности:

- **Схема и хост:** Использование `%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback` в EnvoyFilter позволяет поддерживать правильную схему (http/https) и домен, даже если перед Istio есть внешний балансировщик, меняющий TLS. Убедитесь, что X-Forwarded-Proto правильно проксируется (в стандартном ingress Istio это учтено).
- **TLS:** Поскольку токен OAuth2 (код авторизации, а затем JWT) передается через браузер в query параметре, **обязательно** используйте HTTPS на внешнем интерфейсе. В противном случае код мог бы быть перехвачен. (Если Istio terminaет TLS, то от клиента трафик идёт по HTTPS до ingressgateway).
- **Соответствие порта:** Если gateway слушает на нестандартном порту или вы используете порт в redirect URI, учтите это в настройках Keycloak. Обычно достаточно указать `https://your-host/callback` без порта, если используется стандартный 443.
- **Sign-out (выход):** В конфиге фильтра можно указать `signout_path: /signout`. Если пользователь открывает `https://httpbin.lima/signout`, EnvoyFilter удалит OAuth2-cookies, что по сути разлогинит локальную сессию. (Можно после этого тоже перенаправить на Keycloak logout endpoint вручную или просто показать сообщение). Маршрут `/signout` аналогично можно добавить в VirtualService, если планируется использовать.

После всех настроек, последовательность должна быть такой: пользователь переходит на защищённый URL → Istio (EnvoyFilter) redirect на Keycloak → Keycloak логин → redirect обратно на `/callback` → EnvoyFilter обрабатывает, ставит JWT в cookie/header → пользователь автоматически получает доступ к исходному ресурсу.

## Хранение и передача токена: Cookie vs Authorization Header

При интеграции OAuth2 в веб-приложение есть два основных способа доставлять JWT токен до сервиса: через **cookie** или через **HTTP-заголовок Authorization** (Bearer token). Envoy OAuth2 фильтр способен использовать **оба способа одновременно** (как было задано `forward_bearer_token: true`). Рассмотрим особенности каждого подхода:

| **Способ передачи токена**       | **Описание и преимущества**                                                                                        | **Недостатки и особенности**                                             |
|----------------------------------|--------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| **HTTP-Only Cookie** (сеанс в куки)| – Токен (JWT) сохраняется в браузере в виде cookie (например, `BearerToken`). Браузер автоматически отправляет cookie при каждом запросе на домен, что удобно для обычной навигации по веб-сайту ([json - JWT vs cookies for token-based authentication - Stack Overflow](https://stackoverflow.com/questions/37582444/jwt-vs-cookies-for-token-based-authentication#:~:text=The%20biggest%20difference%20between%20bearer,explicitly%20to%20the%20HTTP%20request)).<br>– Cookie можно пометить флагами **Secure, HttpOnly, SameSite** для безопасности. HttpOnly не позволяет JavaScript читать токен, снижая риск кражи при XSS ([json - JWT vs cookies for token-based authentication - Stack Overflow](https://stackoverflow.com/questions/37582444/jwt-vs-cookies-for-token-based-authentication#:~:text=automatically%20along%20with%20requests%2C%20they,able%20to%20read%20the%20cookie)).<br>– Реализация “из коробки” через Envoy: фильтр сам устанавливает cookie и проверяет его на каждом запросе (по HMAC). Разработчику не нужно писать код работы с JWT на стороне клиента. | – **Уязвимость к CSRF:** браузер отправляет cookie автоматически, поэтому вредоносная страница может попытаться сделать запрос от имени пользователя (например, через скрытую форму). Без защиты (например, CSRF-токенов или SameSite=strict) злоумышленник мог бы заставить браузер выполнить действие от имени авторизованного пользователя ([json - JWT vs cookies for token-based authentication - Stack Overflow](https://stackoverflow.com/questions/37582444/jwt-vs-cookies-for-token-based-authentication#:~:text=The%20browser%20automatically%20sending%20cookies,browser%20into%20executing%20a%20request)) ([json - JWT vs cookies for token-based authentication - Stack Overflow](https://stackoverflow.com/questions/37582444/jwt-vs-cookies-for-token-based-authentication#:~:text=Cookies%20can%20also%20be%20used,send%20cookies%20to%20another%20domain)). Для API, изменяющих данные, нужно внедрять меры против CSRF.<br>– Cookie привязаны к домену. Нельзя поделиться JWT cookie между разными доменами (в нашем случае это не проблема, т.к. токен нужен только на `httpbin.lima`). Но если фронтенд и API на разных доменах, cookie не будет отправлен на другой домен без особых настроек (CORS + credentials).<br>– Ограниченный размер: JWT может быть довольно большим (несколько КБ), что подходит для cookie, но надо быть внимательным, чтобы не превышать лимиты браузеров по размеру заголовка Cookie. |
| **Authorization Header** (Bearer)| – Токен передается в HTTP-заголовке `Authorization: Bearer <JWT>`. Это удобно для **API и скриптов**: токен можно хранить в памяти или локальном хранилище и добавлять к запросам. Браузер сам не отправляет такой заголовок – его контролирует приложение, поэтому запросы выполняются только когда вы их явно делаете (невосприимчиво к CSRF атакам без компрометации токена) ([json - JWT vs cookies for token-based authentication - Stack Overflow](https://stackoverflow.com/questions/37582444/jwt-vs-cookies-for-token-based-authentication#:~:text=The%20biggest%20difference%20between%20bearer,explicitly%20to%20the%20HTTP%20request)).<br>– Хорошо подходит для случаев, когда клиент – не браузер, а, например, мобильное приложение или другой сервис (они не оперируют cookie, но могут вставлять Bearer токен в запросы).<br>– Простая интеграция с существующими схемами авторизации: многие сервисы ожидают Authorization заголовок и имеют готовые middleware для JWT. | – Потребуется клиентский код для хранения и вставки токена. В случае SPA в браузере токен часто хранят в `localStorage` или памяти, что делает его **уязвимым для XSS**: вредоносный скрипт, выполненный на странице, может украсть токен из JS-памяти ([json - JWT vs cookies for token-based authentication - Stack Overflow](https://stackoverflow.com/questions/37582444/jwt-vs-cookies-for-token-based-authentication#:~:text=XSS%3A%20an%20attacker%20embeds%20a,those%20tokens%2C%20and%20also%20send)). (Cookie с HttpOnly, наоборот, от XSS защищён, но страдает от CSRF).<br>– Браузер при переходе по ссылкам не будет автоматически включать заголовок Authorization. То есть стандартный переход по URL не сохранит сессию. Authorization Bearer полезен в AJAX-запросах, но не помогает для простых переходов страниц. Для веб-сайта это означало бы, что каждую страницу нужно загружать через XHR или управлять через скрипт, что сложно. Потому Bearer токены чаще используются для чистых API (например, single-page application, где навигация управляется самим приложением).<br>– Требуется обеспечить безопасное хранение токена на клиенте. Нельзя сохранять долгоживущий JWT в незащищённом виде; часто используют короткоживущий access-token + refresh-token (refresh держат HttpOnly в куки, а access в памяти). Такие сложные схемы требуют дополнительной реализации. |
| **Оба способа (комбинированно)** | – Envoy по умолчанию может использовать оба подхода вместе. В нашем примере `forward_bearer_token: true` означает, что после логина фильтр **установит токен в cookie** *и* параллельно **прикрепит его в Authorization заголовок** при проксировании запроса ([OAuth2 — envoy 1.35.0-dev-1e896b documentation](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/oauth2_filter#:~:text=When%20the%20authn%20server%20validates,populated%20with%20the%20same%20value)). Это даёт лучшую совместимость: обычные браузерные переходы работают за счёт cookie, а серверная часть или Istio могут получать токен из заголовка для проверки или логики.<br>– `pass_through_matcher` позволяет принимать уже имеющиеся Bearer-токены. Например, если в какой-то сценарий ваш клиент (скрипт) получил JWT и посылает его напрямую, Envoy не будет перенаправлять на Keycloak. Таким образом, **интерактивные пользователи** могут работать с cookie, а **клиенты/скрипты** – с заголовками. | – Комбинированный режим объединяет плюсы и минусы обоих. Cookie всё равно присутствует (значит, нужно думать о CSRF для опасных операций на вашем сервисе). Одновременно токен находится и в браузере (в HttpOnly cookie), и передается в заголовке (хоть и не доступен JS напрямую). В целом, этот режим рекомендуется, так как обеспечивает наибольшую совместимость, но следует учитывать упомянутые риски.<br>– При использовании только EnvoyFilter (без модификации приложения) основная защита от XSS/CSRF ляжет на настройки cookie: обязательно включите **Secure** и **HttpOnly** для cookies (EnvoyFilter делает это по умолчанию), а также **SameSite=Lax/Strict** для снижения риска CSRF. Если же ваш фронтенд сам манипулирует токенами, то комбинированный режим может быть избыточен. |

**Рекомендации по выбору:** В контексте Istio + EnvoyFilter (когда прокси сам обрабатывает аутентификацию) обычно используется cookie-подход, дополняемый Authorization заголовком. Это позволяет приложению вовсе не знать о JWT – Istio проверит его, а входящий HTTP запрос в сервис уже будет авторизован. Если же ваше приложение *само* должно знать информацию о пользователе, вы можете прочитать JWT из заголовка Authorization или декодировать его (например, чтобы узнать имя пользователя и т.п.). При `forward_bearer_token: true` токен будет доступен и приложению.

Альтернативный вариант – **только Bearer-токен без cookies** – чаще встречается при использовании внешних прокси вроде oauth2-proxy или в SPA-приложениях, где вам нужно больше контроля. В чисто Istio-сценарии без EnvoyFilter это могло бы выглядеть так: переадресация неиспользованных запросов на отдельный OAuth2 Proxy сервис, а клиентское приложение хранит JWT само. Однако, раз мы используем встроенный OAuth2-фильтр Envoy, имеет смысл задействовать его возможности по установке cookie.

Подытожим:

- **EnvoyFilter + cookie** обеспечивает прозрачную аутентификацию для пользователя и простоту для приложения (сессия как бы “на уровне прокси”). Рекомендуется для сценариев, когда вы защищаете веб-страницы (как `httpbin`) и хотите минимизировать собственный код аутентификации.
- **Authorization header** полезен, если у вас предусмотрены сценарии прямого API-доступа или вы пишете SPA, но в таком случае возможно вы бы использовали другой подход. В нашем решении этот способ поддержан через `pass_through_matcher`.
- Оба способа можно безопасно сочетать. Как видно, Envoy задаёт cookie `BearerToken` и параллельно добавляет Authorization заголовок с тем же токеном ([OAuth2 — envoy 1.35.0-dev-1e896b documentation](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/oauth2_filter#:~:text=When%20the%20authn%20server%20validates,populated%20with%20the%20same%20value)). Это удобный и **безопасный по умолчанию** вариант, т.к. EnvoyFilter сам позаботится о валидации токена (JWT фильтр Istio проверит RS256 подпись), а cookie защищены HMAC-подписью от подделки ([OAuth2-based authentication on Istio-powered Kubernetes clusters - GetInData](https://getindata.com/blog/OAuth2-based-authentication-on-Istio-powered-Kubernetes-clusters/#:~:text=temporary%20authorization%20code%20there,the%20filter%20sets%203%20cookies)). 

Несмотря на то, что JWT-токены самодостаточны, **не полагайтесь только на доверие cookie**. Всегда верифицируйте токен (что и делает Istio JWT authn) и применяйте AuthorizationPolicy, чтобы незалогиненые запросы или токены с неправильными полями не прошли. В итоге, при правильной настройке, вы получите единый безопасный поток: **Keycloak (OIDC, RS256)** → **EnvoyFilter (перенаправление + установка cookies/JWT)** → **Istio JWT проверка** → **доступ к сервису**. Пользователь сохраняет сессию благодаря cookie, а сервис может доверять входящим запросам, зная что Istio проверил JWT.

