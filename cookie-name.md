## Главное в двух словах

Ошибка «OpenID authentication failed» чаще всего сводится к тому, что Kiali не видит собственную сессионную cookie после редиректа от IdP. Это случается, когда **(а)** cookie выдаётся на неправильный `Path`, **(б)** атрибут `SameSite` или имя cookie блокирует её возврат браузером, **(в)** запрошены `scopes`, которых IdP не поддерживает, либо **(г)** старые версии Kiali имеют баг с путевыми префиксами. Ниже — проверка по пунктам, начиная с самых частых причин и заканчивая тонкой отладкой.

---

## 1  Проверьте версию и баг‑фиксы

* Начиная с `v1.72` Kiali починил работу за reverse‑proxy с путём `/kiali` — раньше сессию «съедал» сам UI и возникали точно такие же логи (“session not found”, 401) ([GitHub][1]).
* Поэтому, если у вас ≤ `v1.71`, сразу обновитесь до актуальной `v2.11.x` или новее ([kiali.io][2]).

---

## 2  Имя cookie = `kiali-token-<cluster_name>`

Kiali формирует имя сессионной cookie из поля `spec.server.cluster_name`.
Если это поле пустое, он подставит «Kubernetes», но в логе у вас фигурирует `...-db-dev-kli6-uk-cluster-01`.
Убедитесь, что:

```yaml
spec:
  server:
    cluster_name: db-dev-kli6-uk-cluster-01   # строго то же, что в сообщении лога
```

Иначе UI ищет cookie с одним именем, а backend — с другим, и вы видите «cookie … does not exist» ([GitHub][3]).

---

## 3  Правильный `web_root` и публичный маршрут

Если Kiali открыт по `https://…/kiali/`, в CR должно быть именно так (без завершающего `/`):

```yaml
spec:
  server:
    web_root: "/kiali"
    web_fqdn: "kiali.intranet.corp.com"
    web_schema: "https"
```

Документация подчёркивает, что `web_root` «получает особое обращение» и **должен** начинаться с `/`, но без слеша в конце ([kiali.io][4]). Несоответствие пути → браузер не отправляет cookie → «session not found».

---

## 4  Ingress: переписываем Set‑Cookie → `Path=/kiali`

NGINX‑Ingress по умолчанию оставит атрибут `Path=/`, тогда он не совпадает с реальным URL `/kiali/…`. Добавьте аннотацию:

```yaml
metadata:
  annotations:
    nginx.ingress.kubernetes.io/proxy-cookie-path: / /kiali
```

Эта аннотация переписывает `Set-Cookie` в ответе, и Kiali снова увидит свою cookie ([GitHub][5]). Проверьте в DevTools, что после логина появляется cookie с `Path=/kiali`.

---

## 5  SameSite и HTTPS

Начиная с Chrome 80, кросс‑доменные редиректы требуют `SameSite=None; Secure`.
В Kiali можно задать:

```yaml
spec:
  session:
    same_site: None        # Lax по умолчанию
    secure:   true         # добавит 'Secure'
```

Без этого браузер отбрасывает cookie во втором шаге OIDC ([CookieScript][6]).

---

## 6  Список `scopes` — только то, что поддерживает IdP

В warning “Configured OpenID provider informs some of the configured scopes are unsupported” Kiali печатает ответ discovery‑документа.
Оставьте минимум:

```yaml
spec:
  auth:
    strategy: openid
    openid:
      scopes: ["openid","email"]
```

Те же рекомендации в официальном гайде ([kiali.io][7]) и в типичной разборке проблемы ([GitHub][8]).

---

## 7  Redirect URI строго до `/api/oidc/login`

Хотя вы зарегистрировали `https://…/kiali/`, сам фронтенд посылает код на
`/kiali/api/oidc/login`. Убедитесь, что именно этот адрес присутствует в списке разрешённых callback‑URL клиента CIDP ([kiali.io][7]).

---

## 8  Secret `oidc-secret` и валидатор CR

* Секрет должен находиться в той же namespace, где Pod Kiali, и иметь ключ `oidc-secret`.
* Запустите встроенный валидатор:

  ```bash
  kiali-operator verify --cr kiali.yaml
  ```

  Неправильные поля (`auth.openid.session.cookie`, env‑vars в yaml) сразу всплывут ([GitHub][8]).

---

## 9  Доп. отладка

| Что смотреть                           | Где искать                           | О чём говорит                                                                             |
| -------------------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------- |
| Cookie появляется, но не идёт в запрос | DevTools → Application               | проблема `Path`/`SameSite`                                                                |
| Cookie не создаётся вовсе              | DevTools → Network, вкладка response | Ingress режет `Set‑Cookie`; проверьте аннотацию                                           |
| 401 приходит от K8s API                | логи Kiali (`debug`)                 | значит, токен прошёл, но кластер не доверяет IdP — проверьте флаги `--oidc-*` у apiserver |
| JWT пустой/без `aud`                   | decode на jwt.io                     | добавьте `audience` в AzureAD/Keycloak                                                    |

Полный набор ключевых лог‑строк и их расшифровку можно найти в обсуждениях ([GitHub][9], [GitHub][10]).

---

## 10  Итого чек‑лист

1. **Версия ≥ v2.11** (исключаем старый баг). ([kiali.io][2])
2. `spec.server.cluster_name` совпадает с именем в логе. ([GitHub][3])
3. `web_root=/kiali`, `web_fqdn`, `web_schema=https`. ([kiali.io][4])
4. Ingress → `proxy-cookie-path: / /kiali`. ([GitHub][5])
5. `session.same_site=None`, `session.secure=true`. ([CookieScript][6])
6. В CR только поддерживаемые `scopes`. ([kiali.io][7])
7. Callback URI = `…/kiali/api/oidc/login` в CIDP. ([kiali.io][7])
8. Secret `oidc-secret` на месте, CR проходит валидатор. ([GitHub][8])

Пройдитесь по порядку — в 90 % случаев после п. 4 логин начинает работать. Если где‑то застрянете — покажите конкретный шаг и лог‑строку, разберём глубже.

[1]: https://github.com/kiali/kiali/issues/4459?utm_source=chatgpt.com "Kiali deployed behind proxy does not work as expected · Issue #4459"
[2]: https://kiali.io/news/release-notes/?utm_source=chatgpt.com "Release Notes | Kiali"
[3]: https://github.com/kiali/kiali/blob/master/config/config.go?utm_source=chatgpt.com "kiali/config/config.go at master - GitHub"
[4]: https://kiali.io/docs/installation/installation-guide/accessing-kiali/ "Accessing Kiali | Kiali"
[5]: https://github.com/Shopify/ingress/blob/master/docs/user-guide/nginx-configuration/annotations.md?utm_source=chatgpt.com "ingress/docs/user-guide/nginx-configuration/annotations.md at master"
[6]: https://cookie-script.com/documentation/samesite-cookie-attribute-explained?utm_source=chatgpt.com "SameSite Cookie Attribute explained"
[7]: https://kiali.io/docs/configuration/authentication/openid/ "OpenID Connect strategy | Kiali"
[8]: https://github.com/kiali/kiali/discussions/8177 "Authentication rejected: request failed 401 Unauthorized · kiali kiali · Discussion #8177 · GitHub"
[9]: https://github.com/kiali/kiali/discussions/3571 "Cookie kiali-token-openid-nonce rjected, as expired · kiali kiali · Discussion #3571 · GitHub"
[10]: https://github.com/kiali/kiali/discussions/3716?utm_source=chatgpt.com "Not handling OpenId code flow authentication: No nonce ... - GitHub"
