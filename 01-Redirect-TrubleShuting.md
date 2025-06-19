**Коротко:**
Сообщение CIDP *«Request Error. The server unable to complete the request»* появляется ещё **до** того, как ваше приложение получит `code`/`state`-пару обратно: после успешного ввода логина Google пытается вызвать ваш `redirect_uri`, а затем Envoy должен обменять `code` на `access_token`. Чаще всего цепочка рвётся на одном из четырёх мест:

1. неверный `client_secret` или политика Google *Internal / In production* → ответ `invalid_client`;
2. `redirect_uri` совпадает в Google Console, но **не** совпадает байт-в-байт в самом запросе (лишний слэш, `http` vs `https`) → ответ `invalid_request`;
3. Envoy не может достучаться до `https://oauth2.googleapis.com/token` (egress-ACL, DNS, SNI/TLS) → таймаут 5 с, затем 500;
4. Envoy успешно получил токен, но не сумел сохранить куки (слишком большой `BearerToken`, > 4 K) и повторяет редирект по кругу.

Ниже — как локализовать причину и что проверить в конфигурации.

---

## 1. Как выглядит нормальный обмен

```
Browser ──► CIDP (accounts.google.com) ──► redirect_uri
                         ▲                         │
                         │        POST /token      │
                     Envoy.oauth2 filter ◄─────────┘
```

* После логина CIDP делает **302** на `https://<host>/callback?code=…&state=…`.
* Фильтр Envoy замечает `redirect_path_matcher`, шлёт `POST /token` на кластер `google_oauth2` и получает JSON `{access_token,…}`  ([envoyproxy.io][1]).
* При успехе выставляются куки `BearerToken`, `OAuthHMAC` и запрашиваемый URL отдается 200.

Если где-то в этих шагах возникает ошибка, CIDP показывает общий экран *Request Error* — деталь уходит в ответ JSON, который браузер не показывает  ([oauth.com][2]).

---

## 2. Точки, где всё ломается, и признаки в логах Envoy

| Симптом в конфиге/логе                                                        | Вероятная причина                                                                           | Лог Envoy / HTTP-код           | Что проверить                                                                                                                                                                                        |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `authorization failed, error=invalid_client`                                  | wrong `client_secret` или приложение помечено Google как *Internal* (тест user не добавлен) | `token_endpoint responded 400` | Сравните `client_id/secret` с тем, что скачан из **OAuth 2.0 Client Credentials**; проверьте вкладку *OAuth consent screen* → *Test users*  ([developers.google.com][3], [developers.google.com][4]) |
| `invalid_grant`, `code was already redeemed`                                  | двойной обмен кода (браузер ретрай, redirect-loop)                                          | 400                            | Убедитесь, что `redirect_path_matcher` совпадает ровно один раз и что нет промежуточных 302  ([github.com][5])                                                                                       |
| `upstream connect error or disconnect/reset`                                  | egress-политика, DNS, SNI, self-signed CA                                                   | 503 / 504                      | Пингуйте `curl https://oauth2.googleapis.com/token` из sidecar; добавьте `dns_lookup_family: V4_ONLY` и `upstream_tls_context` если нужен кастомный CA  ([github.com][6])                            |
| Цикл редиректов, браузер хранит куки > 4 K, Chrome пишет *COOKIE\_TOO\_LARGE* | длинный JWT ± refresh\_token                                                                | 302-loop без 400/500           | Ограничьте `access_token` до-минимума, включите `access_token_cookies: { cookie_format: jwe }` или уменьшите scope  ([github.com][5])                                                                |
| Сразу экран Google *Error 400: invalid\_request*                              | `redirect_uri` отличается / содержит фрагмент                                               | 400                            | Сравните URI в адресной строке и в **Credentials → Authorized redirect URIs** (без `/` на конце!)  ([stackoverflow.com][7])                                                                          |

---

## 3. Мини-чек-лист диагностики

1. **DevTools → Network**
   В момент ошибки найдите запрос `POST https://oauth2.googleapis.com/token`.

   * 200 + JSON `error=invalid_client` → неверный секрет;
   * 400 `invalid_request` → URI mismatch;
   * нет запроса вовсе → Envoy не перехватил callback.

2. **Логи прокси**
   В pod со sidecar установите

   ```bash
   export PROXY_CONFIG=debug
   kubectl logs <pod> -c istio-proxy -f | grep oauth2
   ```

   Ошибка валидации (`Proto constraint validation…`) или `unknown cluster` показывает, что фильтр не прочитал config  ([envoyproxy.io][1]).

3. **Проверка egress**

   ```bash
   kubectl exec -it <pod> -c istio-proxy -- curl -v https://oauth2.googleapis.com/token
   ```

   TLS-handshake должен пройти. Если нет — внесите `outboundTrafficPolicy: ALLOW_ANY` или откройте порт 443.

4. **Куки**
   Если токен принимается, но сразу идёт второй редирект, посмотрите размеры `BearerToken`, `OAuthHMAC` в вкладке `Application → Cookies`.

---

## 4. Что поправить в манифесте EnvoyFilter

```yaml
http_filters:
- name: envoy.filters.http.oauth2
  typed_config:
    ...
    token_endpoint:
      cluster: google_oauth2
      uri: https://oauth2.googleapis.com/token
      timeout: 3s
      # 🔽 важно: Google принимает Basic-auth
      authorization_type: basic
    credentials:
      client_id:  "...apps.googleusercontent.com"
      token_secret:  { name: token, sds_config: { path: /etc/envoy/token.yaml } }
      hmac_secret:   { name: hmac,  sds_config: { path: /etc/envoy/hmac.yaml } }
    forward_bearer_token: true
    auth_scopes: ["openid","email"]
```

* Пара `token_secret` + `hmac_secret` обязательна  ([envoyproxy.io][1]).
* Для Google нужно `authorization_type: basic`; иначе клиентские учётки передаются в теле и API отвечает `invalid_client`  ([github.com][8]).
* Таймаут ≥ 3 с — короткий таймаут даёт 504 и CIDP покажет внутреннюю ошибку.

---

## 5. Специфика Google Cloud Identity Platform

* **Test users / Publishing status** — пока приложение в статусе *Testing*, в систему могут войти только e-mail-ы из списка. Неавторизованный пользователь тоже увидит общий *Request Error*  ([support.google.com][9]).
* **Проверка безопасности apps** — если Google заподозрит, что redirect URI не защищён HTTPS или приложение не прошло верификацию, вернётся `invalid_request`  ([stackoverflow.com][7]).
* **Синхронизация времени** — подпись JWT от Envoy содержит `iat/exp`; при сдвиге > 5 минут Google вернёт `invalid_grant`  ([stackoverflow.com][10]).

---

## 6. Итоговый список, что проверить

1. [ ] `client_id` и `client_secret` точны, приложение переведено в *Production* или тестовый пользователь добавлен.
2. [ ] `redirect_uri` в Google Console ≡ `redirect_uri` в фильтре, без лишних слешей.
3. [ ] У sidecar есть egress к `oauth2.googleapis.com:443`, SNI включён.
4. [ ] В фильтре указан `authorization_type: basic`.
5. [ ] Размер куки < 4096 байт, иначе включена JWE-упаковка.
6. [ ] Часы в кластере синхронизированы (NTP).

---

## 7. Что делать дальше

*Соберите и пришлите*:

```bash
# первые 100 строк после рестарта прокси
kubectl logs <pod> -c istio-proxy --tail=100

# Network-trace из DevTools в HAR
```

С этими данными можно точно увидеть, на каком шаге CIDP выдаёт ошибку и какой именно HTTP-код скрывается под общим сообщением.

[1]: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/oauth2_filter?utm_source=chatgpt.com "OAuth2 — envoy 1.35.0-dev-6242c9 documentation"
[2]: https://www.oauth.com/oauth2-servers/server-side-apps/possible-errors/?utm_source=chatgpt.com "Possible Errors - OAuth 2.0 Simplified"
[3]: https://developers.google.com/identity/protocols/oauth2/web-server?utm_source=chatgpt.com "Using OAuth 2.0 for Web Server Applications | Authorization"
[4]: https://developers.google.com/identity/protocols/oauth2/service-account?utm_source=chatgpt.com "Using OAuth 2.0 for Server to Server Applications"
[5]: https://github.com/envoyproxy/envoy/issues/27875?utm_source=chatgpt.com "oauth2 filter: browser blocks BearerToken cookie because its size ..."
[6]: https://github.com/istio/istio/issues/47572?utm_source=chatgpt.com "Oauth flow failed during Envoy oauth2 filter · Issue #47572 - GitHub"
[7]: https://stackoverflow.com/questions/71318804/google-oauth-2-0-failing-with-error-400-invalid-request-for-some-client-id-but?utm_source=chatgpt.com "Google OAuth 2.0 failing with Error 400: invalid_request for some ..."
[8]: https://github.com/SocialiteProviders/Providers/issues/564?utm_source=chatgpt.com "Google Provider - 401 Invalid Client / Unauthorized · Issue #564"
[9]: https://support.google.com/cloudidentity/answer/2463723?hl=en&utm_source=chatgpt.com "Troubleshoot single sign-on (SSO) - Cloud Identity Help"
[10]: https://stackoverflow.com/questions/10576386/invalid-grant-trying-to-get-oauth-token-from-google?utm_source=chatgpt.com "invalid_grant trying to get OAuth token from Google - Stack Overflow"
