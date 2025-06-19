`ERR_TOO_MANY_REDIRECTS` означает, что браузер каждый раз начинает OAuth-процесс заново — Envoy не распознаёт, что пользователь уже вернулся с `/callback`. 99 % случаев сводятся к одному из четырёх сбоев:

1. **Callback-URL не совпадает с `redirect_path_matcher`** — фильтр решает, что это «обычный» запрос и снова уводит на IdP ([envoyproxy.io][1]).
2. **Авторизационные cookies не доходят до Envoy** (SameSite / Secure / domain / path) ([envoyproxy.io][2], [github.com][3], [stackoverflow.com][4]).
3. **`x-forwarded-proto` подменяется** на `http`, из-за чего `redirect_uri` выходит «неправильным» ([stackoverflow.com][5]).
4. **Фильтр срабатывает на все пути (assets, `/callback` и т.д.)** и сам себя зацикливает — так называемый *OAuth doom-loop* ([envoyproxy.io][6]).

Ниже пошагово, как найти точную причину и исправить.

---

## 1  Проверяем, что Envoy «узнаёт» callback

| Что смотреть                                     | Комментарий                                                                                                                                       |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`redirect_uri`** и **`redirect_path_matcher`** | Должны совпадать до символа. Если в `redirect_uri` есть `/callback` с префиксом, а матчер — `exact`, возникнет зацикливание ([envoyproxy.io][1]). |
| **`:path` в логе/DevTools**                      | В сети видно, что после `…/callback?code=…` браузер снова уходит на `/` → `/authorize` → … — классическая петля ([stackoverflow.com][7]).         |

> **Быстрый тест**
> Откройте `/callback` напрямую в приватном окне. Если вместо 200 или 302 сразу происходит редирект на IdP — матчер не сработал.

---

## 2  Убеждаемся, что cookies приходят обратно

### 2.1 Основные файлы куки

Envoy выставляет как минимум `OauthHMAC`, `OauthExpires` и (опционально) `BearerToken` ([envoyproxy.io][1]). В Chrome DevTools → **Application → Cookies** проверьте:

* **Domain** — должен быть `.cidpl.dev.gep.db.com` или конкретный поддомен, на котором работает приложение;
* **SameSite=None; Secure** — иначе браузер отбросит «третьесайтовый» cookie — частая причина циклов после февральского 2025 патча Chrome ([envoyproxy.io][2], [github.com][3]).

```yaml
cookie_configs:
  oauth_hmac_cookie_config:
    domain: ".cidpl.dev.gep.db.com"
    same_site: none   # <-- разрешаем third-party
    secure: true
  oauth_expires_cookie_config:
    domain: ".cidpl.dev.gep.db.com"
    same_site: none
    secure: true
```

> Если SameSite перезаписывается внешним балансировщиком (F5, Nginx-Lua и т.д.) — отключите там глобальные правила или добавьте исключение.

### 2.2 Путь cookie

Фильтр ставит куки на `/`.
Если вы указываете `path` в `cookie_config`, убедитесь, что он совпадает с реальной точкой входа (частая ошибка при SPA за /opt/app).

---

## 3  Проверяем заголовки от Ingress-контроллера

* `x-forwarded-proto` **должен остаться `https`** после TLS-терминации.
  При HTTP->Envoy->HTTPS обратно IdP выдаёт `redirect_uri=https://…`, а клиент отправляет `http://…`, что провоцирует новый редирект — петля ([stackoverflow.com][5]).
* Для Istio достаточно аннотации

```yaml
metadata:
  annotations:
    proxy.istio.io/config: |
      proxyMetadata:
        ISTIO_META_REQUESTED_SERVER_NAME: "devi.cidpl.dev.gep.db.com"
```

---

## 4  Ограничиваем круг URL, где работает фильтр

По умолчанию он включён на **все** запросы; статика (`.js`, `.css`, `/favicon.ico`) тоже уходит в OAuth — ещё одна классическая петля ([envoyproxy.io][6]).

```yaml
pass_through_matcher:
  - name: ":path"
    prefix_match: "/healthz"
  - name: ":path"
    suffix_match: ".css"
  - name: ":path"
    suffix_match: ".js"
```

Используйте `invert_match: true`, если хотите whitelist-подход (см. пример ([stackoverflow.com][5])).

---

## 5  Контрольный список (от простого к сложному)

1. [ ] `redirect_uri` и `redirect_path_matcher` совпадают.
2. [ ] В DevTools после входа видны `OauthHMAC` и `OauthExpires`, Domain совпадает с host.
3. [ ] SameSite=None; Secure стоят (или SameSite вообще отсутствует).
4. [ ] В логе Envoy нет строки `no hmac_secret supplied` (требуется с 1.23+) ([envoyproxy.io][6]).
5. [ ] `x-forwarded-proto=https` доходит до Envoy.
6. [ ] Статические ресурсы и `/callback` исключены через `pass_through_matcher`.

---

## 6  Если зацикливание остаётся

* Включите детальный лог:

  ```bash
  kubectl -n istio-system set env deployment/istio-ingressgateway PROXY_LOG_LEVEL=debug
  ```

  Ищите повторяющиеся строки `redirecting to authorization_endpoint…`.
* Проверьте, что CIDP действительно возвращает **302 на `/callback`** (а не 307/308, которые браузер кэширует) ([envoyproxy.io][1]).
* Убедитесь, что время в Pod и браузере синхронизировано — просроченный `exp` в JWT тоже вызывает повторную авторизацию ([bookstack.cn][8]).

---

### Полезные ссылки

* Envoy OAuth2 flow и роль `redirect_path_matcher` ([envoyproxy.io][1])
* Документация по `cookie_configs.same_site` ([envoyproxy.io][2])
* Пример SPA-сценария и «OAuth doom-loop» ([envoyproxy.io][6])
* Пример Istio-EnvoyFilter c `x-forwarded-proto` и `pass_through_matcher` ([stackoverflow.com][5])
* Разбор циклов из-за SameSite на GitHub ([github.com][3])
* Типичные «CSRF cookie not found» ошибки ([stackoverflow.com][4])
* Случай бесконечной петли в Spring OAuth (анатомия проблемы) ([stackoverflow.com][7])

---

Попробуйте пройтись по чек-листу; в большинстве интеграций с CIDP причиной оказывается именно SameSite или несоответствие `redirect_path_matcher`. Если останутся вопросы — пришлите фрагмент текущего EnvoyFilter и первые 50 строк лога после попытки входа, посмотрим глубже.

[1]: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/oauth2_filter?utm_source=chatgpt.com "OAuth2 — envoy 1.35.0-dev-6242c9 documentation"
[2]: https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/http/oauth2/v3/oauth.proto?utm_source=chatgpt.com "OAuth (proto) — envoy 1.35.0-dev-418953 documentation"
[3]: https://github.com/oauth2-proxy/oauth2-proxy/issues/2830?utm_source=chatgpt.com "[Support]: Unable to find a valid CSRF token when being redirected ..."
[4]: https://stackoverflow.com/questions/77504002/oauth2-proxy-and-subdomains-unable-to-obtain-csrf-cookie?utm_source=chatgpt.com "oauth2-proxy and subdomains - unable to obtain CSRF cookie"
[5]: https://stackoverflow.com/questions/72818784/implement-envoy-oauth2-filter-with-disabled-routes "oauth 2.0 - Implement Envoy OAuth2 filter with disabled routes - Stack Overflow"
[6]: https://www.envoyproxy.io/docs/envoy/latest/start/sandboxes/single-page-app "Single page React app (with OAuth) — envoy 1.35.0-dev-a0f7f0 documentation"
[7]: https://stackoverflow.com/questions/62388299/spring-security-oauth2-client-too-many-redirect "java - Spring security oauth2 client - too many redirect - Stack Overflow"
[8]: https://www.bookstack.cn/read/envoy-1.21-en/1485ae5003444e40.md?utm_source=chatgpt.com "OAuth2 - 《Envoy Proxy 1.21 Documentation》 - 书栈网 · BookStack"
