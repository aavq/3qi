**Ключевой вывод.** `kiali‑token‑nonce‑db‑dev‑kli6‑uk‑cluster‑01` — это **временная (“nonce”) cookie**, которую UI Kiali создаёт перед тем, как отправить пользователя на IdP. После успешного возврата с IdP сервер Kiali должен выдать **вторую** cookie — `kiali‑token‑db‑dev‑kli6‑uk‑cluster‑01` (без «‑nonce‑»). Именно эту вторую cookie ищет backend; если её нет, в логе и UI появляется ошибка «session not found: cookie … does not exist». Следовательно:

* Само наличие nonce‑cookie — нормально и **не** причина ошибки ([GitHub][1]).
* Ошибка говорит о том, что **финальная cookie‑токен не была установлена или не ушла в браузере**.

Ниже разбор, почему это может случаться и как проверить.

---

## 1. Как Kiali использует две cookie

| Стадия                         | Имя cookie                    | Задача                              | Где удаляется                                 |
| ------------------------------ | ----------------------------- | ----------------------------------- | --------------------------------------------- |
| **1.** Перед редиректом        | `kiali‑token‑nonce‑<cluster>` | Защитный nonce для проверки “state” | Удаляется сервером после успешной авторизации |
| **2.** После `/api/oidc/login` | `kiali‑token‑<cluster>`       | Хранит ID‑токен пользователя        | Живёт весь срок сессии                        |

Механизм подробно обсуждался в issue #3711 и #3571 — там же видно, что отсутствие второй cookie ведёт к 401 при первом же REST‑запросе ([GitHub][2], [GitHub][3]).

---

## 2. Что уже правильно

* **Path** в браузере = `/kiali` — ровно то, что должен видеть сервер, если вы оставляете UI за префиксом `/kiali` ([GitHub][1]).
* **Имя кластера** (`db‑dev‑kli6‑uk‑cluster‑01`) встроено в cookie, значит `server.cluster_name` читает корректно ([GitHub][4]).

---

## 3. Почему нет финальной cookie‑токена

### 3.1 `Set‑Cookie` не доходит до браузера

* Среди частых причин — слой Istio Ingress, NGINX или другой proxy, который **не переписывает `Path`/`SameSite`** во втором ответе, либо оставляет только первый заголовок `Set‑Cookie` ([GitHub][2], [GitHub][1]).
* Во многих Lua‑примерaх фильтр ищет ровно строку `Path=/;` — если токен‑cookie приходит уже с `Path=/kiali`, она проходит мимо.

### 3.2 `SameSite` и `Secure`

* В 2.5 флаг `SameSite=None; Secure` ещё не настраивается, поэтому Kiali ставит `SameSite=Lax` 📎 Chrome пропускает Lax при навигации, но Edge/FF могут отбросить cookie, если в ответе POST‑редирект (FAPI hard‑ening) ([Stack Overflow][5], [PortSwigger][6]).

### 3.3 Ошибка внутри `/api/oidc/login`

* Если IdP отклоняет код (неподдерживаемый scope, неверный client\_id и т.п.), backend Kiali не сформирует токен‑cookie и вернёт 401. В логе при `log_level=debug` это выглядит как
  `DBG Token error: Unauthorized` ([GitHub][7]).

---

## 4. Как отладить точку сбоя

| Шаг   | Инструмент                                   | Что должно быть                                                                                        |
| ----- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **1** | DevTools → Network → поиск `/api/oidc/login` | **Ответ 302 или 303** со вторым `Set‑Cookie: kiali‑token‑…; Path=/kiali`                               |
| **2** | DevTools → Application → Cookies             | После редиректа видны **две** cookie: nonce (сразу истекает) и токен (Expires > сейчас)                |
| **3** | `istioctl pc filter <ingress>`               | В Lua‑фильтре проверяем, что замена `Path=/` → `/kiali` срабатывает для **обеих** cookie ([GitHub][2]) |
| **4** | Лог Kiali                                    | Нет строк `No nonce code present` или `Token error` после `/api/oidc/login` ([GitHub][8])              |

---

## 5. Исправления, которые чаще всего помогают

### 5.1 Допилить Lua‑фильтр

Используйте регулярное выражение, чтобы ловить и nonce‑, и токен‑cookie:

```lua
if key == "set-cookie" 
   and string.find(val, "kiali%-token")            -- ловит оба
   and not string.find(val, "Path=/kiali") then
  headers:replace(key, string.gsub(val, "Path=/[^;]*", "Path=/kiali"))
end
```

Так путь будет переписан независимо от того, какое значение стояло изначально. (Алгоритм подсмотрен в рабочих примерах Istio‑Ingress ([GitHub][2], [kubernetes.github.io][9])).

### 5.2 Поменять стратегию маршрутизации

**Простой вариант** — убрать префикс `/kiali` во VirtualService (rewrite на корень), тогда cookie с `Path=/` подходит без фильтра ([kubernetes.github.io][10]).

### 5.3 Проверить scopes и redirect URI

Оставьте только поддерживаемые IdP scope’ы:

```yaml
auth:
  strategy: openid
  openid:
    scopes: ["openid","email"]
```

Слишком широкий список часто рвёт обмен кодом ([kiali.io][11]).
Redirect‑URI в консоли IdP должен быть ровно:
`https://kiali.intranet.corp.com/kiali/api/oidc/login` ([GitHub][12]).

---

## 6. Что делать, если токен‑cookie появилась, но 401 сохраняется

1. Временно установите `auth.openid.disable_rbac: true` — если UI заработает, проблема в доверии Kubernetes API к IdP ([GitHub][8]).
2. Проверьте, что токен содержит `aud=kiali` и подписан ключом из `jwks_uri` discovery‑документа IdP.
3. Убедитесь, что на API‑сервере включены те же параметры `--oidc-issuer-url` и `--oidc-client-id`.

---

## 7. Резюме контрольного списка

| ✔︎  | Проверка                                                  | Где/чем                               |
| --- | --------------------------------------------------------- | ------------------------------------- |
|     | `Set‑Cookie` с токен‑cookie реально приходит              | DevTools → `/api/oidc/login`          |
|     | Lua‑фильтр или rewrite ставит `Path=/kiali`               | `istioctl pc filter` / VirtualService |
|     | В браузере две cookie, имя второй без `‑nonce‑`           | DevTools → Application                |
|     | `scopes` минимальны, redirect URI совпадает               | ConfigMap / консоль IdP               |
|     | В логах Kiali нет `Token error`                           | `kubectl logs`                        |
|     | При 401 сняли `disable_rbac:false` и проверили API‑сервер | kube‑apiserver flags                  |

Пройдите пункты по порядку — обычно токен‑cookie «теряется» именно на этапе маршрутизации или из‑за лишних `scopes`. После того как в браузере появится **вторая** cookie без `‑nonce‑`, ошибка «session not found» исчезнет, и Kiali авторизуется без 401. Если после этих шагов токен всё ещё не создаётся, пришлите тело ответа `/api/oidc/login` и свежий фрагмент лога — посмотрим следующую деталь.

[1]: https://github.com/kiali/kiali/discussions/3571?utm_source=chatgpt.com "Cookie kiali-token-openid-nonce rjected, as expired #3571 - GitHub"
[2]: https://github.com/kiali/kiali/discussions/3716?utm_source=chatgpt.com "Not handling OpenId code flow authentication: No nonce ... - GitHub"
[3]: https://github.com/kiali/kiali/issues/3711?utm_source=chatgpt.com "Not handling OpenId code flow authentication: No nonce ... - GitHub"
[4]: https://github.com/kiali/kiali/blob/master/config/config.go?utm_source=chatgpt.com "kiali/config/config.go at master - GitHub"
[5]: https://stackoverflow.com/questions/77114367/samesite-strict-behavior-after-oidc-login?utm_source=chatgpt.com "Samesite=Strict behavior after oidc login - cookies - Stack Overflow"
[6]: https://portswigger.net/web-security/csrf/bypassing-samesite-restrictions?utm_source=chatgpt.com "Bypassing SameSite cookie restrictions | Web Security Academy"
[7]: https://github.com/kiali/kiali/issues/3410?utm_source=chatgpt.com "Unable to authenticate with OIDC and Google OpenID connect #3410"
[8]: https://github.com/kiali/kiali/discussions/3889?utm_source=chatgpt.com "cannot use kiali and gcp/google openid #3889 - GitHub"
[9]: https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/configmap/?utm_source=chatgpt.com "ConfigMap - Ingress-Nginx Controller - Kubernetes"
[10]: https://kubernetes.github.io/ingress-nginx/examples/rewrite/?utm_source=chatgpt.com "Rewrite - Ingress-Nginx Controller - Kubernetes"
[11]: https://kiali.io/docs/configuration/authentication/openid/?utm_source=chatgpt.com "OpenID Connect strategy - Kiali"
[12]: https://github.com/kiali/kiali/discussions/4243?utm_source=chatgpt.com "Issue in setting up Kiali openid connect using Azure AD OAuth. #4243"
