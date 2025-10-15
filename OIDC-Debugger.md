Понимаю задачу: нужно изолировать проблемы не ковыряя Kiali и быстро проверить, что **сам ClientID/redirect/scopes в CIDP работают**. Ниже — короткая, “чек-листовая” структура причин и минимальные тесты для их исключения.

# 1) Регистрация клиента у CIDP (метаданные)

**Что ломается:** `redirect_uri_mismatch`, `invalid_client`, PKCE-ошибки, неверные scopes.
**Проверь:**

* Точный **Redirect URI** (протокол/хост/порт/путь/слэш в конце, www/не-www). Это самый частый фейл. ([Stack Overflow][1])
* Тип клиента (confidential/public), **нужен ли PKCE**.
* Точные **scopes** (минимум `openid`; Kiali по умолчанию тянет `openid profile email`). ([kiali.io][2])
* Выданный **client_secret** актуален, клиент не заблокирован.
* Что **issuer/.well-known** указывает на правильные endpoints (authorize, token, jwks).

# 2) Этап авторизации (GET /authorize)

**Симптомы:** ошибка сразу на IdP: `unauthorized_client`, `invalid_scope`, политика доступа.
**Мини-тест:** собрать запрос через **OIDC Debugger** — он помогает собрать `authorize` URL и увидеть ответ/редирект. Для работы нужно, чтобы в allowlist был `https://oidcdebugger.com/debug` (или `oauthdebugger.com/debug`). Если доезжаешь до **`code`** — этот этап у тебя ОК. ([oidcdebugger.com][3])

# 3) Редирект обратно (callback)

**Симптомы:** есть `code`, но приложение “теряется”; или браузер блокирует возврат/сессию.
**Причины:** неправильно зарегистрированный **redirect_uri**; **state/nonce** не совпал; или на callback-странице не ставится сессионная cookie из-за **SameSite/Secure**.
**Замечание:** для кросс-сайтовых OIDC-редиректов cookie часто требуют `SameSite=None; Secure`. Иначе браузер их не пришлёт на возврате. ([Microsoft Learn][4])

# 4) Обмен кода на токены (POST /token)

**Симптомы:** `invalid_grant`, `unauthorized_client`, `unsupported_grant_type`.
**Частые причины:**

* Неправильная клиентская аутентификация (**client_secret_basic** vs **client_secret_post**).
* Забыли передать **redirect_uri** в токен-запросе.
* Включён **PKCE**, но не передали `code_verifier`.
  **Мини-тест:** добейся полного обмена в инструменте (см. п. “Стенд” ниже) и посмотри детальную ошибку. ([Logto blog][5])

# 5) Содержимое и валидация токенов

**Симптомы в приложении:** “успешный логин”, но Kiali/прокси отвергает токен.
**Проверь:**

* В `id_token` **`iss`** ровно совпадает с discovery, **`aud/azp`** соответствует твоему `client_id`.
* Нужные **claims** реально приходят (например, `email`, `groups`) — иначе маппинг пользователей/доступов ломается. (Kiali по умолчанию берёт `sub`, можно переключить на `email`.) ([kiali.io][2])

# 6) Redirect-URI: локалхост/петля (для CLI/десктоп-проверок)

Если хочешь тестировать с локальным callback без внешнего хоста, IdP должен разрешать **loopback redirect** (`http://127.0.0.1:{port}/callback`) по RFC 8252; часто порт можно варьировать. Если у вашего CIDP это не включено — используйте заранее разрешённый внешний redirect. ([IETF Datatracker][6])

# 7) Сеть/сертификаты/прокси

**Симптомы:** таймауты, ошибка при скачивании ключей (JWKS), проблемы только “за прокси”.
**Проверь:** доверие к CA (внутренние сертификаты), прокси-переменные и доступность discovery/JWKS. В Kiali для самоподписанных CA есть отдельные настройки — это типичная точка сбоя в прод-сетях. ([kiali.io][2])

---

## Мини-стенд для проверки ClientID без изменения Kiali

Выбирай любой из трёх — все дают **быстрые итерации**:

1. **OIDC Debugger (браузер)** — проверяешь только этап **/authorize → code**. Нужен заранее разрешённый redirect `https://oidcdebugger.com/debug`. Быстро выявляет ошибки регистрации (`redirect_uri`, `scope`, политика). ([oidcdebugger.com][3])

2. **Postman (полный обмен кода на токены)** — в Authorization выбери **Authorization Code**, поставь **Callback URL** `https://oauth.pstmn.io/v1/callback` (этот URL должен быть в allowlist у CIDP), укажи **client_id/secret**, endpoints из discovery; Postman сам откроет браузер, вернётся на callback и обменяет код на **access_token/id_token**. ([Postman Docs][7])

3. **CLI oauth2c** — кроссплатформенный инструмент, умеет PKCE/разные client-auth методы и локальный callback (если CIDP разрешает loopback). Удобно, когда надо точно контролировать `code_verifier` и способ клиентской аутентификации. ([GitHub][8])

---

## Как читать результаты и быстро локализовать

* **Если не получаешь `code`** в (1)/(2): проблемы регистрации клиента (redirect/политика/scopes).
* **Если `code` есть, но /token падает:** способ клиентской аутентификации, `code_verifier/PKCE`, отсутствие `redirect_uri` в теле запроса. ([Logto blog][5])
* **Если токены пришли, но приложение не “логинит”:** проверь `iss/aud/azp/exp/nbf`, нужные `claims` и cookie-поведение на callback (SameSite/Secure). ([Microsoft Learn][4])

---

## Почему это релевантно для твоего кейса с Kiali

Kiali использует **Authorization Code Flow** и по умолчанию запрашивает `openid profile email`. Большая часть “магии” — стандартный OIDC-флоу. Если вне Kiali ты стабильно получаешь `code` и обмениваешь его на валидные токены, значит проблема **не в CIDP**, а в интеграции (redirect-URL Kiali, cookie на callback, доверие к CA/прокси или маппинг claims). ([kiali.io][2])

---

Хочешь — дальше дам **пошаговый рецепт** для каждого варианта стенда (OIDC Debugger → Postman → oauth2c), чек-команды и примеры успешных/ошибочных ответов, чтобы за 10–15 минут понять, где именно рвётся.

[1]: https://stackoverflow.com/questions/11485271/google-oauth-2-authorization-error-redirect-uri-mismatch?utm_source=chatgpt.com "Google OAuth 2 authorization - Error: redirect_uri_mismatch"
[2]: https://kiali.io/docs/configuration/authentication/openid/ "OpenID Connect strategy | Kiali"
[3]: https://oidcdebugger.com/?utm_source=chatgpt.com "OpenID Connect Debugger: Create a request"
[4]: https://learn.microsoft.com/en-us/aspnet/core/security/samesite?view=aspnetcore-9.0&utm_source=chatgpt.com "Work with SameSite cookies in ASP.NET Core"
[5]: https://blog.logto.io/troubleshoot-invalid-grant-error?utm_source=chatgpt.com "Exploring OIDC grants: understanding and troubleshooting ..."
[6]: https://datatracker.ietf.org/doc/html/rfc8252?utm_source=chatgpt.com "RFC 8252 - OAuth 2.0 for Native Apps"
[7]: https://learning.postman.com/docs/sending-requests/authorization/oauth-20/?utm_source=chatgpt.com "Authenticate with OAuth 2.0 authentication in Postman"
[8]: https://github.com/SecureAuthCorp/oauth2c?utm_source=chatgpt.com "SecureAuthCorp/oauth2c: User-friendly OAuth2 CLI"


---
---
---

Да, есть. По твоим симптомам видно, что авторизация у IdP проходит (редирект обратно в Kiali есть), а вот установка/чтение **сессии Kiali** срывается. Ниже — короткий, «боевой» чек-лист именно под твои логи.

# Что проверить по порядку

1. **Секрет клиента и обмен кода на токен**
   В логах Kiali по невалидному client_secret часто видно что-то вроде `OpenId token request failed: unauthorized_client/Invalid client credentials`. У Kiali секрет берётся из секрета `kiali` (ключ `oidc-secret`) в неймспейсе установки. Убедись, что:
   – секрет существует и ключ называется **строго** `oidc-secret` (base64),
   – `issuer_uri` задан правильно (URI провайдера/realm, а не `/authorize`),
   – client_id совпадает с зарегистрированным у IdP.
   Это прямо описано в доке Kiali по OpenID и примерах создания секрета. ([Kiali][1])

2. **Redirect URL и «корневой путь» Kiali**
   У Kiali callback — это **корень инстанса** (например, `https://host/kiali`). В клиенте у IdP должен быть разрешён именно этот URL (и точное совпадение со схемой/хостом/путём). ([Kiali][1])

3. **X-Forwarded-*** (частая причина у банков за прокси/ингрессом)
   Если Kiali за LB/Ingress, он вычисляет «правильный» внешний адрес по `X-Forwarded-Proto/Host/Port`. При их отсутствии бывает редирект на `http` или с портом 20001, и браузер/IdP режут куки/совпадение redirect_uri. Явно проставь хотя бы `X-Forwarded-Port: 443` на входе в Kiali (в Istio VirtualService, Ingress и т.д.). ([Kiali][2])

4. **Куки Kiali не устанавливаются / не доходят**
   Твой лог `session not found: cookie kiali-token-... does not exist in request` прямо об этом. Проверь в DevTools: на ответе Kiali **после колбэка** (`/kiali/api/auth/openid_callback`/`openid_redirect`) есть ли заголовок `Set-Cookie` с вида `kiali-token-*`. Если `Set-Cookie` есть, но следующая просьба к `/kiali/api/...` уходит **без** этой куки — смотри атрибуты:
   – требуется `SameSite=None; Secure` для кук, участвующих в кросс-сайте/редиректе, иначе браузер их не пошлёт;
   – домен/путь должен соответствовать хосту и префиксу `/kiali`.
   (Это уже политика браузеров: Chrome отправляет «внешние» куки только с `SameSite=None; Secure`.) ([Google for Developers][3])

5. **Скоупы**
   Kiali по умолчанию просит `openid profile email`. Если IdP в метаданных сообщает, что часть скоупов не поддерживается, Kiali пишет warning как у тебя и вход может падать. Для диагностики **сведи к минимуму**: попроси у IdP только `openid` (временно), либо убедись, что `email`/`profile` реально разрешены для твоего клиента. Это поведение и настройка скоупов описаны в Kiali docs. ([Kiali][1])

6. **Имя куки сессии (краевой кейс)**
   Бывали случаи, когда помогала явная установка имени куки в CR Kiali (`spec.auth.session.cookie.name`). Проверь, как именно называется кука в `Set-Cookie`, и задай такое имя в CR — в похожем кейсе это решило проблему. ([GitHub][4])

7. **Kiali за прокси и вычисление внешнего URL**
   Если путь/хост «снаружи» не совпадают с тем, что видит Kiali «внутри», он может формировать неверные редиректы. Помимо `X-Forwarded-*` можно задать внешний URL через аннотацию `kiali.io/external-url` или соответствующие настройки экспонирования (см. раздел про доступ к Kiali). ([Kiali][5])

8. **TLS/CA IdP**
   Если у IdP внутренний CA, не отключай валидацию наугад — лучше добавить корневой CA через `kiali-cabundle` (а не `insecure_skip_verify_tls: true`). Это штатный путь в Kiali OpenID. ([Kiali][1])

9. **Не гоняйся за «login failed» — не лочись**
   Пока не проверишь пункты выше, не повторяй попытки одним и тем же юзером — IdP может залочить учётку. Тестируй в приватном окне (чтобы не мешали старые куки/кэш).

---

## Как быстро локализовать корень (минимальный сценарий)

1. Открой DevTools → Network. Пройди логин один раз.
2. На запросе **колбэка в Kiali** посмотри:
   – статус 302/200? нет ли в ответе ошибок;
   – есть ли `Set-Cookie: kiali-token-*` и какие атрибуты (Domain/Path/SameSite/Secure).
3. На **первом** запросе к `/kiali/api/auth/status` или любой API-ручке — уходит ли кука?
   – **Нет** → проблема в атрибутах/домене/пути/ SameSite/прокси (см. п.3–4,7).
   – **Да** → смотри логи Kiali на момент обмена кода на токен (секрет/issuer/доступ к IdP) — часто видно `unauthorized_client` либо ошибки до токена (см. п.1). ([GitHub][4])

---

## «Банково-безопасный» способ проверить сам клиент IdP (без ковыряния Kiali)

Если внешние инструменты запрещены, сделай **внутри контура** крошечный «OIDC code-flow проверятор» (один Pod/Service на разрешённом хосте из списка redirect_uri у IdP), который:

1. делает `/authorize` → принимает `code` →
2. меняет `code` на токены на `token_endpoint` тем же `client_id/client_secret` →
3. печатает ID-токен/claims.

Так ты отделишь: «клиент у IdP работает / Kiali не принимает куку» от «клиент у IdP не работает вовсе». Если совсем без стенда — можно временно поставить Kiali за **oauth2-proxy** и переключить Kiali на стратегию `header`, чтобы прокси взял на себя OIDC и отдал Kiali готовый заголовок; это тоже банковый паттерн. ([Kiali][6])

---

### Коротко: что у тебя наиболее вероятно

* Неверный/недоступный **client_secret** (или секрет не в `kiali/oidc-secret`) → Kiali не получает токен и не ставит сессию. ([Kiali][1])
* Неправильные **X-Forwarded-*** → неверный redirect / проблемы с кукой. ([Kiali][2])
* Кука ставится, но не отправляется из-за **SameSite/Secure/Domain/Path** → «cookie … does not exist in request». ([Google for Developers][3])
* Запрошены **несуществующие скоупы** → предупреждение в логах и возможный срыв входа; сузить до `openid`. ([Kiali][1])

Если хочешь, дам готовый минимальный nginx/Flask-манифест для внутреннего «OIDC-проверятора» под твоё доменное имя и один из разрешённых redirect_uri — это позволяет проверить **именно** этот ClientID/секрет/скоупы на действующем CIDP, вообще не трогая конфиг Kiali.

[1]: https://kiali.io/docs/configuration/authentication/openid/ "OpenID Connect strategy | Kiali"
[2]: https://kiali.io/docs/faq/authentication/ "Authentication | Kiali"
[3]: https://developers.google.com/search/blog/2020/01/get-ready-for-new-samesitenone-secure?utm_source=chatgpt.com "Get Ready for New SameSite=None; Secure Cookie Settings"
[4]: https://github.com/kiali/kiali/discussions/8177?utm_source=chatgpt.com "Authentication rejected: request failed 401 Unauthorized"
[5]: https://kiali.io/docs/installation/installation-guide/accessing-kiali/?utm_source=chatgpt.com "Accessing Kiali"
[6]: https://kiali.io/docs/configuration/authentication/header/?utm_source=chatgpt.com "Header strategy"


---
---
---


Вот готовый черновик письма. Я оставил плейсхолдеры в угловых скобках — просто подставь свои значения.

---

**Subject:** Request to verify OIDC client configuration for Kiali (Client ID: `<CLIENT_ID>`)

**Hi CIDP team,**

We are integrating **Kiali** with our corporate IdP via **OIDC Authorization Code** flow and are seeing an authentication failure that appears to happen **on the IdP side before the redirect back to Kiali**.

**What’s configured on our side (Kiali):**

* Auth strategy: **openid** (Authorization Code flow).
* `issuer_uri`: `<ISSUER_ISSUER_URL>` (realm/tenant used for this client).
* `client_id`: `<CLIENT_ID>`.
* `client_secret`: stored in the `kiali` secret (key `oidc-secret`) in the install namespace.
* `scopes`: currently requesting `openid profile email` (can reduce to `openid` if needed).
* `redirect_uri`: `https://<KIALI_HOST>/kiali` (exact match, no trailing slash).
* Kiali is published via `<INGRESS/ISTIO GATEWAY/LOAD-BALANCER>`, forwarding `X-Forwarded-Proto/Host/Port`.

**Observed symptoms:**

* After I enter credentials on the CIDP login page, the browser console shows **401** on IdP endpoints like:

  * `authenticate?goto=<...>`
  * `sessions?_action=getSessionInfo` (multiple times)
* No redirect back to Kiali occurs; Kiali then shows **“login failed”**.
* Kiali logs include:

  * `Could not read the session: session not found: cookie kiali-token-... does not exist in request`
  * `Configured OpenID provider informs some of the configured scopes are unsupported. Users may not be able to login.`
* After several attempts I see **“Warning: You will be locked out after N more failure(s)”** on the IdP page.

This looks like the IdP login flow isn’t completing (no SSO session or it isn’t recognized), or my user isn’t authorized for this client, so the browser never gets redirected back with a code.

**Could you please check and confirm the following for `<CLIENT_ID>` and my user `<MY_UPN/LOGIN>`:**

1. **Client registration / metadata**

* The **Redirect URIs** include exactly: `https://<KIALI_HOST>/kiali` (character-for-character; scheme/host/port/path; no trailing slash).
* **Response type** `code` (Authorization Code) is allowed; **response mode** `query` (and/or `form_post`) is allowed.
* **Token endpoint auth method** permitted for this client (`client_secret_basic` and/or `client_secret_post`).
* Whether **PKCE (S256)** is required for this client.
* The discovery endpoints for this realm/tenant (authorize/token/jwks) used by this client.

2. **User assignment / entitlements**

* Is my user **assigned/entitled** to this application/client (or a group that is allowed)?
* If your platform has “user assignment required” or similar, please confirm my account is assigned and allowed to obtain tokens for `<CLIENT_ID>`.
* Confirm the **realm/journey** used for authentication and that there’s no conditional policy (MFA step, IP policy, group condition, attribute requirement) blocking my user.

3. **Scopes and claims**

* Which **scopes** are allowed for `<CLIENT_ID>`? Are `openid`, `profile`, `email` all supported?
* If some scopes are **unsupported**, please specify the allowed minimal set (we can switch to `openid` only).
* Which **ID token claims** will be present (`sub`, `email`, `groups`, etc.)? If group claims are available, what is their claim name/format?

4. **Session / cookies during login page**

* After successful primary auth, does the IdP set its **SSO/session cookie** (name and attributes)?
* Please confirm its attributes support cross-site redirects (**`SameSite=None; Secure`**), so the subsequent calls like `sessions?_action=getSessionInfo` don’t return 401 due to the cookie being dropped by the browser.
* Is the **`goto`** target host `https://<KIALI_HOST>` allowed by your policies/whitelist?

5. **Audit / error details for my recent attempts**

* For my attempts at approximately `<DATE TIME TZ>`, could you provide the audit entries or the **exact error** (reason string / policy node) returned by the IdP that leads to the 401 on `authenticate`/`sessions`?
* If the flow reached authorization and a **code** was issued, did you see a subsequent **/token** request from Kiali? If yes, what was the result/status, and was there any error such as `invalid_client`, `unauthorized_client`, or `invalid_grant`?

6. **Lockout policy**

* Because I am now close to lockout, could you **reset/relax** the lockout for my account during troubleshooting or provide a **temporary test account** that is known to be assigned to `<CLIENT_ID>`?

If you confirm the items above (especially user assignment, allowed scopes, redirect/goto whitelist, cookie attributes, and the client’s token auth method), I can immediately re-test and, if needed, adjust our side (e.g., scopes and headers like `X-Forwarded-Proto/Host/Port`).

Thank you!

Best regards,
`<Your Name>`
`<Team / Project>`
`<Contact>`

---

### Notes for you (не отправлять в письмо)

* Kiali поддерживает только **Authorization Code** flow и по умолчанию использует `openid profile email`; redirect обычно `https://<host>/kiali`. ([kiali.io][1])
* 401 на `sessions?_action=getSessionInfo` и `authenticate?goto=` типичны для ForgeRock/PingAM-подобных IdP, когда **SSO-cookie не установилась/не вернулась** или пользователь не авторизован на приложение. ([backstage.forgerock.com][2])
* Для кросс-сайтовых сценариев важно, чтобы SSO-cookie IdP имела **`SameSite=None; Secure`** — иначе браузер её не пошлёт на следующие REST-вызовы, и IdP ответит 401. ([Google for Developers][3])
* В системах вроде Entra ID «**User assignment required**» блокирует выдачу токена, если пользователь/группа не назначены на приложение. ([Microsoft Learn][4])

Хочешь, адаптирую письмо под конкретные значения (`<CLIENT_ID>`, точные время/URL, realm, скриншоты из DevTools) — просто кинь их сюда, и я быстро подставлю.

[1]: https://kiali.io/docs/configuration/authentication/openid/?utm_source=chatgpt.com "OpenID Connect strategy"
[2]: https://backstage.forgerock.com/docs/am/7.1/sessions-guide/managing-sessions-REST.html?utm_source=chatgpt.com "Managing Sessions (REST) - ForgeRock Backstage"
[3]: https://developers.google.com/search/blog/2020/01/get-ready-for-new-samesitenone-secure?utm_source=chatgpt.com "Get Ready for New SameSite=None; Secure Cookie Settings"
[4]: https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/application-properties?utm_source=chatgpt.com "Properties of an enterprise application - Microsoft Entra ID"

---
---
---


