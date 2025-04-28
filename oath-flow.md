## 1. Istio + Envoy OAuth2 Filter (EnvoyFilter `httpbin-oauth`)

> **Цель:** заставить sidecar Envoy на входе в Pod httpbin выполнять полное OAuth 2.0/OIDC-аутентифицирование пользователя, прежде чем запрос попадёт в контейнер приложения.

| Этап | Действие | Ключевые детали конфигурации |
|------|----------|-----------------------------|
| 1 | **Клиент посылает HTTP-запрос к `httpbin`** | Нет маркера — запрос не соответствует `pass_through_matcher`. |
| 2 | **Inbound-listener Envoy** улавливает запрос | Фильтр `envoy.filters.http.oauth2` вставлен первым (`INSERT_FIRST`) перед обычным `router`. |
| 3 | **Проверка «пропусков»** | URI `/callback` и `/healthz/ready`, либо уже присутствующий заголовок `Authorization: Bearer …` — пропускаются без аутентификации. |
| 4 | **Редирект 302 на IdP** | `authorization_endpoint` ⇒ `https://idp.lima/…/auth`, параметр `redirect_uri` собирается из заголовков запроса. |
| 5 | **Пользователь проходит логин/consent** | На стороне IdP. В конце IdP посылает браузер на `/callback?code=…` |
| 6 | **Код авторизации → токен** | Envoy по кластеру `idp-oauth-cluster` (`LOGICAL_DNS`, TLS SNI `idp.lima`) вызывает `token_endpoint` и получает `access_token`, `id_token`, (опционально) `refresh_token`. |
| 7 | **Формирование cookie и заголовков** | - Записываются cookie `BearerToken`, `OauthExpires`, подпись HMAC. <br> - `forward_bearer_token: true` — Envoy добавляет `Authorization: Bearer …` к проксируемому запросу. |
| 8 | **Передача в контейнер `httpbin`** | Запрос считается аутентифицированным. |
| 9 | **Автоматическое освежение** | При истечении срока действия Envoy использует `refresh_token`, если `use_refresh_token: true`. |
| 10 | **Выход «logout»** | Запрос на `/logout` удалит cookie и сгенерирует редирект к IdP для logout-endpoint (настраивается в IdP). |

---

## 2. Kubernetes, без Istio/Envoy — NGINX Ingress Controller + OAuth2 Plugin

1. **Клиент** → HTTPS-запрос через Ingress.  
2. **NGINX Lua-плагин (oauth2-proxy, lua-oauth, dex-auth-lua — зависит от реализации)** проверяет:
   - Наличие валидной сессионной cookie или заголовка `Authorization`.  
3. **Нет токена ⇒ 302** на `/oauth2/start`, оттуда — к IdP `https://…/auth`.  
4. **Пользователь авторизуется** на IdP → `/oauth2/callback?code=`.  
5. **Плагин обменивает code на access/ID token**, сохраняет:
   - Encrypted cookie или Redis-сессию.  
6. **Плагин ставит заголовок** `X-Auth-Request-User`, `X-Auth-Request-Email` *или* `Authorization: Bearer …` — как настроено.  
7. **Запрос проксируется к Service/Pod**; приложение доверяет заголовкам или JWT.  
8. **Повторные запросы** проверяются плагином локально, без похода к IdP, пока cookie не истекла.  
9. **/logout** удаляет cookie и редиректит на IdP logout-endpoint.

---

## 3. Kubernetes с Istio и внешним OAuth2 Proxy (двойное звено: OAuth2 Proxy → Envoy)

| Шаг | Поток |
|-----|-------|
| 1 | **Клиент** → HTTPS `svc.example.com` (A-запись на OAuth2 Proxy Service). |
| 2 | **OAuth2 Proxy Pod** (один per-service или shared) принимает запрос.<br>— Если нет сессии → 302 на IdP. |
| 3 | **IdP логин** → back `/oauth2/callback`, proxy обменивает code на tokens, кладёт их в cookie/session. |
| 4 | **OAuth2 Proxy отправляет запрос далее**: <br>`Authorization: Bearer <access_token>` *или* `X-Email`, `X-User`. Адрес получателя — ClusterIP/VirtualService вашего приложения. |
| 5 | **Istio ingress-gateway (если используется)** просто терминат TLS и маршрутизирует в Mesh. |
| 6 | **Envoy sidecar** у самого Pod’a видит уже аутентифицированный запрос. Дополнительных фильтров не нужно. |
| 7 | **Приложение** использует заголовок или проверяет JWT (опционально через Envoy JWT Auth N фильтр). |
| 8 | **Обратный путь** — ответы идут через sidecar → OAuth2 Proxy → клиент. |
| 9 | **Обновление/выход** целиком управляется OAuth2 Proxy (`/oauth2/sign_out`). |

---

## 4. Классический OAuth2 Authorization Code Flow + OIDC (CIDP/EIDP)

> *CIDP/EIDP* — корпоративный или европейский удостоверяющий провайдер (например, Swiss E-ID, BankID, GOV.UA и т.п.).

### Участники
- **Client** — браузер или мобильное приложение.
- **Authorization Server (AS)** — публичный энд-поинт протокола OAuth2.
- **Identity Provider (IdP)** — хранилище учётных данных + OpenID-энд-поинты.
- **Application / Relying Party (RP)** — ваше веб-приложение.

### Пошаговый алгоритм

1. **Запрос защищённого ресурса**:  
   Клиент → RP `/dashboard`.
2. **RP генерирует 302** на AS `/authorize` с параметрами:  
   `response_type=code&client_id=…&scope=openid profile&redirect_uri=https://rp/callback&state=xyz&nonce=abc`.
3. **AS отображает экран логина** или переадресует на IdP (CIDP/EIDP) для eID-аутентификации.  
4. **Пользователь проходит eID-auth + даёт согласие** → AS выдаёт *authorization code* и редиректит браузер на `https://rp/callback?code=abcd&state=xyz`.
5. **RP бек-энд** (сервер-side) POST’ом на `/token` обменивает `code` на:  
   - `access_token` (OAuth2)  
   - `id_token` (JWT, OIDC)  
   - опционально `refresh_token`.
6. **RP проверяет `id_token`:** подпись (JWKS), `aud`, `iss`, `nonce`, время жизни.  
7. **Создание сессии**: в cookie или в SPA-локальном хранилище кладётся:  
   - HttpOnly session-cookie или Bearer JWT.  
8. **Доступ к API**:  
   Клиент → RP API с `Authorization: Bearer <access_token>`; API проверяет токен у AS ( introspection / jwks-verify ).  
9. **Обновление**: при истечении `access_token` браузер/приложение использует `refresh_token` (если присутствует) на энд-поинте `/token` (grant type `refresh_token`).  
10. **Logout**: RP удаляет сессию → 302 на AS `/logout?post_logout_redirect_uri=…`; AS завершает сеанс у IdP.

---

### Как пользоваться этими алгоритмами

- **Точки интеграции**  
  - *Istio-фильтр* — удобен, если весь трафик уже в Service Mesh и нужен inline SSO.  
  - *NGINX Ingress Plugin* — проще установить, если Mesh не нужен.  
  - *Отдельный OAuth2 Proxy* — гибкое решение “адаптер” + совместимо с любыми сервис-мешами.  
- **Валидация безопасности**  
  - Проверяйте `state` и `nonce`, включайте PKCE где возможно.  
  - Минимизируйте срок жизни `access_token`, полагайтесь на *silent refresh*.  
- **Отладка**  
  - Chrome DevTools → вкладка *Network* / *Cookies*.  
  - `istioctl proxy-config` и `envoy_admin` для трассировки фильтров.  

Так вы сможете выбрать и правильно настроить подходящий вариант авторизации для любого сценария.
