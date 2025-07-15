**TL; DR**
Вы ставили Kiali «как в истио‑samples» — без оператора, только Deployment + ConfigMap. В этой схеме:

* **Флаги `session.cookie.same_site/secure` в версии 2.5 ещё не поддерживаются** – они появились только после мержа PR, закрывшего issue #6912 (≈ v2.8+) ([GitHub][1]). Поэтому любые строки с этими ключами просто игнорируются, и браузер продолжает блокировать cookie.
* Параметр `auth.openid.session.cookie.name` тоже не работает: имя вычисляется автоматически как `kiali‑token‑<cluster_name>`; его менять нельзя, надо задать правильный `server.cluster_name` ([GitHub][2]).
* Главная причина «cookie … does not exist» при Istio Ingress Gateway — **атрибут `Path`**. Envoy не умеет переписывать `Set‑Cookie`, поэтому cookie ставится на `/`, а запросы идут на `/kiali/…` и cookie не отправляется ([GitHub][3]).

Ниже план, который надёжно решает проблему.

---

## 1  Обновитесь минимум до Kiali 2.8

* Начиная с **v2.8** Kiali ставит `Secure` на cookie, а в **v2.10** добавлен конфиг `same_site` ([GitHub][4]).
* Helm‑чарт поменял формат ConfigMap: cookie‑поля теперь лежат под `session › cookie` ([GitHub][5]).

  ```yaml
  session:
    cookie:
      same_site: None     # Strict|Lax|None
      secure:    true
  ```
* В Istio‑bundles (`samples/addons/kiali.yaml`) обновлён и web\_root‑патч, исправляющий двойной слэш ([GitHub][2]).

> **Как мигрировать:**
>
> ```
> helm repo add kiali https://kiali.org/helm-charts
> helm upgrade --install kiali-server kiali/kiali-server \
>   --namespace istio-system \
>   --version 2.11.0
> ```
>
> После апгрейда удалите самодельные поля из старой ConfigMap, иначе Kiali не стартует.

---

## 2  Если обновление пока нельзя — чините `Path` в cookie

Istio‑Ingress не умеет `proxy-cookie-path`, но это можно сделать Lua‑фильтром:

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: kiali-cookie-path
  namespace: istio-system
spec:
  workloadSelector:
    labels:
      istio: ingressgateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
      listener:
        filterChain:
          filter:
            name: envoy.filters.network.http_connection_manager
    patch:
      operation: INSERT_BEFORE
      value:
        name: envoy.filters.http.lua
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
          inlineCode: |
            function envoy_on_response(handle)
              local h = handle:headers()
              local c = h:get("set-cookie")
              if c and string.find(c, "kiali-token") and not string.find(c, "Path=/kiali") then
                h:replace("set-cookie", string.gsub(c, "Path=/", "Path=/kiali"))
              end
            end
```

*Фильтр переписывает только cookie Kiali, остальные остаются нетронутыми.* После применения:

1. Очистите старую cookie в браузере.
2. Пройдите логин; в DevTools увидите `kiali-token‑…; Path=/kiali`.

Теперь бекенд найдёт cookie и перестанет писать «session not found».

---

## 3  Проверьте остальные обязательные поля

| Поле                  | Где задаётся                        | Примечание                                                                                    |
| --------------------- | ----------------------------------- | --------------------------------------------------------------------------------------------- |
| `server.web_root`     | ConfigMap → `server > web_root`     | **`/kiali` без завершающего `/`** ([GitHub][2])                                               |
| `server.web_schema`   | `https`                             | иначе Chrome заблокирует `SameSite=None`                                                      |
| `server.web_fqdn`     | `kiali.intranet.corp.com`           | формирует абсолютный redirect URI                                                             |
| `auth.openid.*`       | `client_id`, `issuer_uri`, `scopes` | проверьте, что в discovery‑документе IdP эти `scopes_supported` (иначе warning) ([GitHub][5]) |
| `server.cluster_name` | `db-dev-kli6-uk-cluster-01`         | влияет на имя cookie                                                                          |

---

## 4  Почему изменения в ConfigMap «видны» даже без CR

Manifest из Istio‑samples монтирует `/kiali-configuration/config.yaml` прямо в Pod (см. Deployment шаблон) ([GitHub][2]). Любая правка ConfigMap действительно перезапускает Pod и применяется. Но:

* Синтаксис должен точно повторять **структуру Go‑конфига** (нет `auth.session.…`).
* Неизвестные ключи тихо отбрасываются – именно так произошло с вашим `same_site`/`secure` на 2.5.

---

## 5  Итого

1. **Лучшее решение — апгрейд на ≥ v2.8**: появятся поддерживаемые атрибуты `Secure` и `SameSite`, баг с путями устранён.
2. При невозможности апгрейда — добавьте EnvoyFilter, который перепишет `Path=/` → `/kiali`, и убедитесь, что `web_root`/`cluster_name` заданы правильно.
3. Не редактируйте несуществующие секции (`auth.session.…`) — Kiali их игнорирует.

После применения любого из вариантов сообщение **«session not found: cookie … does not exist»** исчезнет, а кнопка *Login* перестанет ронять 401. Если, выполнив шаги, всё ещё видите ошибку — пришлите строку `Set‑Cookie` из DevTools и первые 20 строк свежего лога Kiali (`INF Server configuration:`), посмотрим дальше.

[1]: https://github.com/kiali/kiali/issues/6912 "GitHub · Where software is built"
[2]: https://raw.githubusercontent.com/istio/istio/release-1.26/samples/addons/kiali.yaml?utm_source=chatgpt.com "samples/addons/kiali.yaml - GitHub"
[3]: https://github.com/kiali/kiali/issues/3103?utm_source=chatgpt.com "oidc redirect to `/kiali` always redirects to `/kiali/` without processing ..."
[4]: https://github.com/kiali/kiali/issues/6912?utm_source=chatgpt.com "Set Secure Attribute on Session Cookie · Issue #6912 - GitHub"
[5]: https://raw.githubusercontent.com/kiali/kiali.io/staging/content/en/docs/Configuration/authentication/openid.md "raw.githubusercontent.com"
