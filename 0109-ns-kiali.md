Ок — то, что смена `scopes` ничего не изменила, ещё сильнее говорит, что падает не «авторизация по ролям», а **сессия Kiali не заводится из-за cookie** (она не ставится на callback или не уходит обратно в запросах). Ниже — «точечный» план проверки именно этой причины с Edge DevTools и с кластера.

---

# 1) Проверка в Edge DevTools (за 5–10 минут)

**Цель:** понять, ставит ли Kiali cookie на callback и почему браузер её потом не отправляет.

1. Открой Kiali по **HTTPS**. Нажми `F12` → вкладка **Network**, включи **Preserve log**.
2. Нажми **Login with OpenID** и пройди логин у IdP. Вернёшься на URL вида:

   * `/kiali/api/auth/openid/callback` или `/api/auth/openid/callback`.
3. В **Network** кликни именно **ответ Kiali** на этот callback → **Headers → Response Headers**:

   * **Ожидаемо:** заголовок **`Set-Cookie: kiali-token-…`**.
   * **Если `Set-Cookie` НЕТ:** сразу переходи к разделу «Если cookie не ставится вовсе».
4. Если `Set-Cookie` **есть**, открой **Application → Storage → Cookies → твой домен** и проверь атрибуты **этой** cookie:

   * **SameSite = None**, **Secure = true** (иначе кросс-сайтовый OIDC-редирект съест cookie). ([Google for Developers][1], [Chromium][2])
   * **Domain/Path** соответствуют твоему реальному URL (если Kiali под префиксом `/kiali`, `Path` должен позволять этот префикс). ([Kiali][3])
   * В **Network** на следующем запросе к Kiali (например, `/api/auth/info`) в **Request Headers** должен появиться `Cookie: kiali-token-…`. Если его нет — Edge часто пишет «Blocked reason» (SameSite/не Secure/не тот домен) в консоли и в карточке запроса. ([Chromium][2])

> Типичный offender — cookie без `SameSite=None; Secure` при доступе через внешний домен/ингресс. Браузер её просто не отправляет после редиректа.

---

# 2) Если cookie **ставится**, но **не уходит** в запросах

Скорее всего, Kiali стоит **за прокси/ingress**, а он не пробрасывает исходную схему/порт/хост — Kiali думает, что трафик был по HTTP: в итоге атрибуты/путь cookie «кривые».

**Действия:**

1. Убедись, что ходишь к Kiali по **HTTPS**.
2. На прокси добавь заголовки, которые Kiali ожидает:

   * `X-Forwarded-Proto: https`, `X-Forwarded-Host: <внешний host>`, **`X-Forwarded-Port: "443"`**.
     Для Istio это можно сделать прямо в `VirtualService` (пример из официального FAQ Kiali):

   ```yaml
   http:
   - headers:
       request:
         set:
           X-Forwarded-Port: "443"
     route:
     - destination:
         host: kiali
         port:
           number: 20001
   ```

   Это штатная рекомендация Kiali для OpenID за прокси. ([Kiali][4])
3. Если публикуешь Kiali **под путём** (например, `https://example.com/kiali`), проверь `spec.server.web_root: "/kiali"` в Kiali CR — от этого зависит базовый **Path** и ресурсы UI. ([Kiali][3])
4. Повтори проверку из раздела 1: на callback должен быть `Set-Cookie`, и в следующем запросе к `/api/...` cookie должна уйти.

---

# 3) Если cookie **не ставится вовсе** на callback

Здесь обмен кода на токен не прошёл (401) и Kiali не дошёл до `Set-Cookie`.

**Проверь по порядку:**

1. **Секрет клиента в кластере.**
   Kiali ждёт `Secret/kiali` (по умолчанию) с ключом **`oidc-secret`**.
   Проверка:

   ```bash
   kubectl -n <ns-kiali> get secret kiali -o jsonpath='{.data.oidc-secret}' | base64 -d; echo
   ```

   Значение должно ровно совпадать с client secret в IdP. Если пусто/не тот — создаёшь/обновляешь:

   ```bash
   kubectl -n <ns-kiali> create secret generic kiali \
     --from-literal=oidc-secret='<CLIENT_SECRET>' \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

   (После — перезапусти Pod Kiali.) Это прямо из доков и обсуждений: при 401 часто банально нет секрета. ([Kiali][5], [GitHub][6])
2. **`issuer_uri` и Discovery.**
   В CR укажи **базовый issuer**, а не `/authorize` или `/token`. Открой в браузере
   `https://<issuer>/.well-known/openid-configuration` — JSON должен открываться и соответствовать твоему `issuer_uri`. Документация Kiali подчёркивает корректность `issuer_uri`. ([Kiali][5])
3. **Redirect URI, зарегистрированный в IdP.**
   У IdP **должен быть разрешён корневой путь твоего Kiali** как callback (например, `https://<host>/kiali`, если Kiali под префиксом). Это требование зафиксировано в официальной инструкции Kiali как при NAC, так и без него. ([Kiali][5])
4. **(На время диагностики) упростить до «без NAC».**
   В CR временно:

   ```yaml
   spec:
     auth:
       strategy: openid
       openid:
         client_id: "<client>"
         issuer_uri: "https://<issuer>"
         disable_rbac: true
         scopes: ["openid"]
   ```

   Это исключает влияние интеграции кластера с OIDC и проверяет чисто связку Kiali↔IdP. (В доках есть оба сценария — с NAC и без.) ([Kiali][5])
5. **Включить DEBUG-логи Kiali.**

   ```bash
   kubectl -n <ns-kiali> patch kiali kiali --type merge -p \
     '{"spec":{"deployment":{"logger":{"log_level":"debug"}}}}'
   kubectl -n <ns-kiali> logs deploy/kiali | grep -i openid -A3 -B3
   ```

   В логе будет видно `unauthorized_client` / `invalid_client` / проблемы TLS к IdP (если внутренний CA). Для внутреннего CA — либо `ConfigMap/kiali-cabundle` с `openid-server-ca.crt`, либо (только на тесте) `insecure_skip_verify_tls: true`. Всё это описано в разделе «Additional configurations». ([Kiali][5])

---

# 4) Короткий чек-лист «почини и проверь»

* [ ] Доступ к Kiali по **HTTPS**.
* [ ] В ingress/gateway проставить `X-Forwarded-Proto/Host/Port` (**порт 443 обязателен**). ([Kiali][4])
* [ ] В CR `spec.server.web_root` совпадает с реальным префиксом публикации (если есть). ([Kiali][3])
* [ ] В CR `auth.strategy: openid`, корректные `client_id`/`issuer_uri` (issuer — **база**, без `/authorize`). ([Kiali][5])
* [ ] В IdP разрешён **root URL Kiali** как **Redirect URI**. ([Kiali][5])
* [ ] `Secret/kiali` содержит **`oidc-secret`** (правильный). ([Kiali][5], [GitHub][6])
* [ ] На callback есть `Set-Cookie: kiali-token-…`; cookie имеет **`SameSite=None; Secure`**, корректные Domain/Path; в следующем запросе cookie уходит. ([Google for Developers][1], [Kiali][3])

---

Если хочешь, скидывай:

1. фрагмент CR `spec.server.web_root` и `spec.auth.openid`;
2. **Response Headers** callback-ответа (кусок с `Set-Cookie`);
3. карточку cookie из **Application → Cookies** (имя/Domain/Path/SameSite/Secure).
   По этим трём штукам можно почти всегда быстро ткнуть в точку, почему Kiali пишет `session not found`.

[1]: https://developers.google.com/search/blog/2020/01/get-ready-for-new-samesitenone-secure?utm_source=chatgpt.com "Get Ready for New SameSite=None; Secure Cookie Settings"
[2]: https://www.chromium.org/updates/same-site/faq/?utm_source=chatgpt.com "SameSite Frequently Asked Questions (FAQ)"
[3]: https://kiali.io/docs/installation/installation-guide/accessing-kiali/?utm_source=chatgpt.com "Accessing Kiali"
[4]: https://kiali.io/docs/faq/authentication/ "Authentication | Kiali"
[5]: https://kiali.io/docs/configuration/authentication/openid/ "OpenID Connect strategy | Kiali"
[6]: https://github.com/kiali/kiali/discussions/4708?utm_source=chatgpt.com "Configuring OpenID on Azure · kiali kiali · Discussion #4708"
