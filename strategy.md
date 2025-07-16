Ниже — пошаговый «чек‑лист» для Kiali 2.5, развёрнутой **через обычный Deployment + ConfigMap** (без оператора). Он показывает, какие поля надо исправить, зачем нужен секрет `oidc‑secret`, почему **не нужно** явно задавать `redirect_uri` в конфиге и как проверить каждую настройку.

---

## В двух словах — что у вас сломано

* В `config.yaml` указана `auth.atrategy: anonymous` (опечатка + неправильная стратегия) — поэтому Kiali даже не включает OIDC‑код.
* Блок `openid` пустой, а секрет `oidc‑secret` Kiali видит, только если стратегия действительно равна `openid`.
* `redirect_uri` вы пытаетесь «прописать вручную», но Kiali всегда формирует **сам** URL == «корневой путь экземпляра» (`https://…/kiali`) и ожидает, что этот exact URL уже занесён в CIDP как callback ([GitHub][1]).

---

## 1  Приводим ConfigMap к рабочему минимуму

```yaml
# ConfigMap/kiali-configuration, key: config.yaml
server:
  web_root: "/kiali"             # без завершающего слэша
  web_schema: "https"
  web_fqdn: "kiali.intranet.corp.com"
  cluster_name: "db-dev-kli6-uk-cluster-01"

auth:
  strategy: "openid"             # было anonymous
  openid:
    issuer_uri: "https://cidp.corp.com/realms/corp"
    client_id: "kiali"           # ID, выданный CIDP
    scopes: ["openid","email"]   # только то, что точно поддерживается
    disable_rbac: true           # оставьте true, пока не наладите токены
```

* `strategy` и `openid.*` — это единственный корректный путь; поля вроде `auth.openid.session.*` или `openshift.*` в версии 2.5 игнорируются ([GitHub][1], [kiali.io][2]).
* `server.web_root` должен начинаться с `/` и **не** оканчиваться `/`; иначе Kiali ошибётся при сборке URL‑ов ([kiali.io][3]).
* Из `cluster_name` Kiali вычисляет окончательное имя cookie (`kiali‑token‑<cluster>`), поэтому оно обязано совпадать с тем, что вы видите в логе ([GitHub][4]).

---

## 2  Секрет с client secret

```bash
kubectl create secret generic kiali \
  -n istio-system \
  --from-literal="oidc-secret=$CLIENT_SECRET"
```

Kiali ищет секрет **по имени `kiali`** и ключу **`oidc-secret`**; без него authorization‑code flow не стартует ([GitHub][1]). После создания перезапустите Pod:

```bash
kubectl rollout restart deploy/kiali -n istio-system
```

---

## 3  Настраиваем клиента в CIDP

1. **Callback / Redirect URI** — ровно `https://kiali.intranet.corp.com/kiali`.
   Kiali передаёт именно этот URL в параметре `redirect_uri`; менять его в конфиге невозможно и не нужно ([GitHub][1]).
2. Включите только стандартные scope’ы `openid` и `email`. Если CIDP автоматически добавляет `profile` — не страшно; но любые кастомные scope’ы, которых нет в `scopes_supported` discovery, вызывают предупреждение и разрывают сессию ([GitHub][1]).
3. Если вы **не** настраивали RBAC‑привязку Kubernetes к этому IdP, оставьте `disable_rbac: true` — так Kiali проверит подпись токена локально и обойдётся без K8s‑API ([GitHub][1]).

---

## 4  Перезапускаем и проверяем

| Что сделать                                             | Где смотреть                                                                               | О чём говорит                                |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------ | -------------------------------------------- |
| 1. Открыть DevTools → Network → `/kiali`                | Ответ 302 на CIDP, затем 302 на `/kiali/`                                                  | OIDC редирект прошёл                         |
| 2. DevTools → Application → Cookies                     | Появились **две** cookie: `kiali-token-nonce-…` **и** `kiali-token-…`; обе с `Path=/kiali` | Норма: nonce и финальный токен ([GitHub][4]) |
| 3. Лог Kiali (level = debug)                            | `INF OpenID provider initialized` и нет строк `session not found`                          | Сессия создана                               |
| 4. Любой REST‑запрос (например `/api/istio/namespaces`) | HTTP 200                                                                                   | Токен принят                                 |

Если токен‑cookie **не** появляется, проверьте, не режет ли Istio Gateway заголовок `Set‑Cookie` или не меняет `Path` (см. баг про требование «/kiali» без слэша ([GitHub][5])).

---

## 5  Частые ловушки

| Симптом                                                 | Причина                                              | Исправление                                                                                                                                    |
| ------------------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `session not found: cookie … does not exist in request` | финальная cookie не была установлена                 | CIDP неправильно настроен, или Istio Ingress меняет `Path`; убедитесь, что cookie имеет `Path=/kiali` и имя без `‑nonce‑` ([GitHub][4])        |
| `OpenID provider informs some scopes are unsupported`   | в `scopes` указано то, чего нет в `scopes_supported` | оставьте `openid`,`email` ([GitHub][1])                                                                                                        |
| 401 после логина, cookie есть                           | кластер API не доверяет IdP                          | пока оставить `disable_rbac: true`; если нужна RBAC‑привязка — добавьте `--oidc-issuer-url`/`--oidc-client-id` на kube‑apiserver ([GitHub][1]) |

---

## 6  Быстрый чек‑лист перед тестом

* **ConfigMap** содержит ровно: `auth.strategy: openid`, заполненный `openid: {issuer_uri, client_id, scopes…}` и корректный блок `server.*` ([pre-v1-41.kiali.io][6]).
* **Секрет `kiali`** в namespace `istio-system`, ключ `oidc-secret` ([Kiali][7]).
* В CIDP разрешён callback `https://kiali.intranet.corp.com/kiali` и подключены только нужные scopes ([GitHub][1]).
* Pod Kiali перезапущен после изменения ConfigMap/Secret ([GitHub][8]).
* В браузере после логина есть cookie `kiali-token-<cluster>` с `Path=/kiali` ([GitHub][4]).

Когда все пункты пройдены, кнопка **Login in Kiali** откроет дашборд без сообщения *OpenID authentication failed*.

[1]: https://raw.githubusercontent.com/kiali/kiali.io/master/content/en/docs/Configuration/authentication/openid.md "raw.githubusercontent.com"
[2]: https://kiali.io/docs/configuration/authentication/openid/?utm_source=chatgpt.com "OpenID Connect strategy - Kiali"
[3]: https://kiali.io/docs/configuration/kialis.kiali.io/?utm_source=chatgpt.com "Kiali CR Reference"
[4]: https://github.com/kiali/kiali/discussions/8177?utm_source=chatgpt.com "Authentication rejected: request failed 401 Unauthorized #8177"
[5]: https://github.com/kiali/kiali/issues/5229?utm_source=chatgpt.com "openid redirects to web_root without · Issue #5229 · kiali/kiali - GitHub"
[6]: https://pre-v1-41.kiali.io/documentation/v1.35/installation-guide/?utm_source=chatgpt.com "Installation Guide - Kiali: Service mesh observability and configuration"
[7]: https://v1-41.kiali.io/docs/configuration/authentication/openid/?utm_source=chatgpt.com "OpenID Connect strategy - Kiali"
[8]: https://github.com/istio/istio/blob/master/samples/addons/kiali.yaml?utm_source=chatgpt.com "istio/samples/addons/kiali.yaml at master - GitHub"
