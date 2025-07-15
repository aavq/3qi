**Сводка‑одной‑фразой.**
У вас уже проходит редирект в CIDP, но Kiali «роняет» сессию по‑дороге обратно: токен не кладётся/не читается из cookie **и** запрошенный в Kiali scope `az1prod` не поддерживается IdP.  В результате Kiali не может обменять код на токен (HTTP 401) и UI показывает *OpenID authentication failed*.  Надёжное решение: (1) убрать неподдерживаемые scope’ы, (2) зафиксировать имя cookie или включить sticky‑session, (3) выдать вашему пользователю/группе роль `kiali-viewer` (или временно включить `disable_rbac: true`).  Ниже — детальный чек‑лист, как это сделать один раз и не возвращаться.

---

## 1 — Что именно ломается

| Симптом в логе                                          | Что значит                            | Основная причина                                                                                                       |
| ------------------------------------------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `Could not read the session: cookie ... does not exist` | Kiali не нашёл свою сессионную cookie | ➊ Ingress/LB отбрасывает `Set‑Cookie`; ➋ Вы вернулись на другой pod (cookie‑name содержит хост); ➌ cookie `Path` ≠ URL |
| `provider informs some scopes are unsupported`          | IdP отверг запрос на `scope`          | В Kiali есть лишний/опечатанный scope (`az1prod`)                                                                      |
| `Authentication rejected: request failed (HTTP 401)`    | Обмен «code→token» не удался          | Из‑за двух строк выше access‑token не получен                                                                          |

Источник примеров лога и причин — обсуждения issue #8177 и #3262 у разработчиков Kiali ([GitHub][1], [GitHub][2]).

---

## 2 — Фикс № 1: привести список **scopes**

1. Откройте **App registration** в CIDP и посмотрите, какие scopes реально объявлены.

2. В `Kiali CR` (или Helm values) оставьте только поддерживаемые:

   ```yaml
   spec:
     auth:
       openid:
         scopes:
           - openid
           - email        # profile тоже безопасно
         # уберите "az1prod" или зарегистрируйте его в IdP
   ```

   Док: Kiali запрашивает *openid, profile, email* по‑умолчанию и выдаёт warning, если что‑то не поддерживается ([kiali.io][3], [kiali.io][3]).

3. `helm upgrade …` или `kubectl apply -f kiali-cr.yaml`.

---

## 3 — Фикс № 2: сохранить/прочитать cookie

### 3.1 Если Kiali **в одном** pod‑е

* Добавьте/проверьте аннотацию Ingress (NGINX):

  ```yaml
  nginx.ingress.kubernetes.io/proxy-cookie-path: /kiali/ /kiali
  ```

  чтобы cookie с `Path=/kiali` возвращалась на все запросы под этим префиксом ([Kiali][4]).

### 3.2 Если Kiali **в нескольких** репликах за LB

* Cookie‑name формируется как `kiali-token-<pod-host>` — когда второй запрос попадает на другой pod, имя не совпадает и лог видит «cookie ... does not exist» ([GitHub][1]).
* Надёжнее всего **зафиксировать имя** (появилось с Kiali v1.78+):

  ```yaml
  spec:
    auth:
      openid:
        session:
          cookie:
            name: kiali-token               # любое единое имя
  ```

  Пример успешного патча в issue #8177 ([GitHub][5]).
* Альтернатива — включить **sticky‑sessions** в Ingress (`nginx.ingress.kubernetes.io/affinity: cookie`) или в Istio Gateway (`sessionAffinityConfig`) ([Kiali][4]).

---

## 4 — Фикс № 3: авторизация в кластере

| Хотите быстрый «view‑only для всех»   | Хотите тонкий RBAC                                                                                                                                                                                                                                                                                                                |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| В CR добавьте<br>`disable_rbac: true` | 1. Проверьте claim, который Kiali берёт из токена (`username_claim: email` по‑умолчанию).<br>2. Выдайте этому **User** или **Group** роль `kiali-viewer`:<br>`yaml<br>kind: ClusterRoleBinding<br>subjects:<br>- kind: User      # или Group<br>  name: ваш@почта<br>roleRef:<br>  kind: ClusterRole<br>  name: kiali-viewer<br>` |

Минимальное право, которое нужно для входа с RBAC — `get namespace` ([kiali.io][6], [pre-v1-41.kiali.io][7]).

---

## 5 — Проверочный чек‑лист

1. **Браузер DevTools → Network → /authorize**
   *Проверить*: в параметре `scope=` нет `az1prod`; `redirect_uri` = `https://kiali.…/kiali`.
2. **Пакет Set‑Cookie** из IdP‑редиректа присутствует, имя совпадает с `session.cookie.name`.
3. ```bash
   kubectl auth can-i get namespaces --as=<email>
   ```

   Вывод `yes`.
4. В логах Kiali за последние 30 с:

   ```bash
   kubectl logs -n kiali deploy/kiali --since=30s \
     | egrep "forbidden|session not found|unsupported"
   ```

   Должно быть пусто.

---

## 6 — Что оставить «на постоянку»

1. **Очищенный список scopes** (без `az1prod` или с новым разрешённым scope).
2. **Фиксированное имя cookie** или sticky‑sessions — иначе при масштабировании проблема вернётся.
3. **ClusterRoleBinding** на группу разработчиков/администраторов с ролью `kiali-viewer` (или своей read‑only).
4. Документируйте эти три пункта в Helm values / Argo overlay, чтобы при следующем апгрейде Kiali всё осталось рабочим.

---

### Если всё ещё видите 401/куки‑ошибку

* Убедитесь, что API‑сервер Kubernetes настроен с `--oidc-issuer-url` и `--oidc-client-id`, совпадающими с Kiali ([GitHub][2]).
* В AKS + AzureAD потребуется `kube‑oidc‑proxy` перед API‑сервером .
* Проверьте, что Ingress/Gateway добавляет `X‑Forwarded‑Proto: https` и `X‑Forwarded‑Port: 443` (иначе IdP вернёт на `http://…:80`) ([Kiali][4], [GitHub][8]).

---

## Полезные ссылки

* Официальная дока по OpenID‑настройке Kiali ([kiali.io][3])
* FAQ: порт и заголовки за прокси ([Kiali][4])
* Namespace/RBAC‑гайд — минимальные права ([kiali.io][6], [pre-v1-41.kiali.io][7])
* Расследование аналогичной ошибки (cookie + 401) в issue #8177 ([GitHub][1])

После этих шагов кнопка **Login with OpenID** должна возвращать вас в Kiali уже под авторизованной сессией — без предупреждений в логе и без повторных redirect’ов. Если появятся новые симптомы — присылайте свежий лог – разберёмся.

[1]: https://github.com/kiali/kiali/discussions/8177 "Authentication rejected: request failed 401 Unauthorized · kiali kiali · Discussion #8177 · GitHub"
[2]: https://github.com/kiali/kiali/issues/3262?utm_source=chatgpt.com "Fail to login with OpenID Connect as \"failure when retrieving user ..."
[3]: https://kiali.io/docs/configuration/authentication/openid/?utm_source=chatgpt.com "OpenID Connect strategy - Kiali"
[4]: https://v1-41.kiali.io/docs/faq/authentication/?utm_source=chatgpt.com "Authentication - Kiali"
[5]: https://github.com/kiali/kiali/discussions/8177?utm_source=chatgpt.com "Authentication rejected: request failed 401 Unauthorized #8177"
[6]: https://kiali.io/docs/configuration/rbac/?utm_source=chatgpt.com "Namespace access control - Kiali"
[7]: https://pre-v1-41.kiali.io/documentation/v1.24/faq/?utm_source=chatgpt.com "FAQ - Kiali: Service mesh observability and configuration"
[8]: https://github.com/kiali/kiali/discussions/6490?utm_source=chatgpt.com "oidc redirect to http always with port 443 #6490 - kiali kiali - GitHub"
