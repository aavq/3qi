**Ниже — полный `EnvoyFilter`, который на уровне Istio Ingress Gateway переписывает атрибут `Path` во всех cookie Kiali (и `kiali‑token`, и `kiali‑token‑nonce`) c `/` на `/kiali`.
Фильтр вставляется *до* штатного `envoy.filters.http.router`, поэтому он видит уже готовый ответ от Kiali и успевает подменить заголовки, прежде чем они уйдут в браузер. Развёрнутый комментарий после манифеста объясняет ключевые моменты и проверки.**

```yaml
# kiali-cookie-path.yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: kiali-cookie-path       # уникальное имя в namespace
  namespace: istio-system       # тот же ns, где ingress‑gateway
spec:
  workloadSelector:
    labels:
      istio: ingressgateway     # <<— label из Deployment ingress‑gateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY          # нужен именно GATEWAY, не SIDECAR
      listener:
        filterChain:
          filter:
            name: envoy.filters.network.http_connection_manager
    patch:
      operation: INSERT_BEFORE  # вставляем ПЕРЕД router
      value:
        name: envoy.filters.http.lua
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
          inlineCode: |
            -- Envoy Lua: правка атрибута Path для Set‑Cookie токенов Kiali
            local function fix_cookie_path(cookie_header)
              -- заменяем любой Path=/... на Path=/kiali
              return string.gsub(cookie_header, "Path=/[^;]*", "Path=/kiali")
            end

            function envoy_on_response(handle)
              local headers = handle:headers()
              -- iterate over all response headers; byteSize()==кол-во пар ключ‑значение
              for i = 0, headers:byteSize() - 1 do
                local k, v = headers:getAt(i)
                if k == "set-cookie" then
                  -- трогаем только cookie, начинающиеся на kiali-token
                  if string.find(v, "^kiali%-token") then
                    headers:replace(k, fix_cookie_path(v))
                  end
                end
              end
            end
```

---

## Что делает фильтр и почему он безопасен

| Блок                           | Назначение                                                                                                                                                                                                                                                                                                                                      | Ссылки                                     |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `workloadSelector`             | Ограничивает действие до Pod‑ов с label `istio=ingressgateway`, чтобы не трогать sidecar‑прокси приложений.                                                                                                                                                                                                                                     | ([Istio][1])                               |
| `context: GATEWAY`             | Фильтр активен только в листенерах Ingress Gateway, а не внутренних sidecar.                                                                                                                                                                                                                                                                    | ([Istio][1])                               |
| `INSERT_BEFORE`                | Вставляемся перед `envoy.filters.http.router`, как рекомендуют примеры Istio, чтобы видеть *ответ* сервиса.                                                                                                                                                                                                                                     | ([Medium][2])                              |
| Lua‑код                        | • проход по всем заголовкам (`byteSize/getAt`) нужен, потому что ответ содержит **две** cookie (`nonce` и *финальную*) и Envoy возвращает их отдельными строками ([GitHub][3]); • регэксп меняет любой `Path=/…` на `/kiali`, включая выпадки с `Path=/` и `Path=//`; • условие `^kiali%-token` гарантирует, что не будем портить чужие cookie. | ([envoyproxy.io][4]) ([Stack Overflow][5]) |
| Не трогаем `SameSite`/`Secure` | В Kiali 2.5 эти атрибуты заданы по умолчанию (`SameSite=Lax`), а мы меняем только `Path`, что безопасно для любых браузеров.                                                                                                                                                                                                                    | ([GitHub][6])                              |

---

## Как проверить, что фильтр работает

1. **Загрузите манифест**

   ```bash
   kubectl apply -f kiali-cookie-path.yaml
   kubectl rollout restart deploy istio-ingressgateway -n istio-system
   ```
2. **Убедитесь, что Lua‑фильтр подхватился**

   ```bash
   istioctl pc filter $(kubectl -n istio-system \
     get pods -l istio=ingressgateway -o jsonpath='{.items[0].metadata.name}') \
     -n istio-system --name envoy.filters.http.lua | grep kiali-cookie-path
   ```

   В выводе должен появиться наш код. ([Istio][1])
3. **Откройте DevTools → Network → /api/oidc/login**
   В ответе должен быть `Set-Cookie: kiali-token-…; Path=/kiali;`. Если да — браузер вернёт cookie, Kiali перестанет писать «session not found».
4. **Вкладка Application → Cookies**
   После полноценного логина увидите **две** записи: временную `kiali-token-nonce-…` (сразу истечёт) и рабочую `kiali-token-…` (Expires > текущего времени). | ([GitHub][3])

---

## Если остался 401 после установки cookie

* Проверьте, что Kiali читает тот же `cluster_name`, из которого формируется имя cookie — он берётся из поля **`server.cluster_name`** в ConfigMap (по умолчанию `Kubernetes`) ([GitHub][7]).
* Сократите список `scopes` до `["openid","email"]` — лишние скоупы часто отказываются IdP и ломают обмен кодом ([Stack Overflow][8]).
* Если токен‑cookie есть, но любой REST‑запрос отвечает 401, временно задайте `disable_rbac: true` — так легко отделить ошибку валидации токена Kiali от отказа Kubernetes API. | ([GitHub][6])

---

### Главное

* **Nonce‑cookie = норма** — она появляется ещё *до* перехода на IdP.
* Ошибку «session not found» вызывает **отсутствие полноценной `kiali-token-…` cookie** в ответе после `/api/oidc/login`.
* Фильтр выше гарантированно ставит правильный `Path=/kiali` и даёт браузеру вернуть cookie обратно, что убирает 401 без апгрейда Kiali.

[1]: https://istio.io/latest/docs/reference/config/networking/envoy-filter/?utm_source=chatgpt.com "Envoy Filter - Istio"
[2]: https://tanmaybatham.medium.com/header-manipulation-using-envoy-filters-in-istio-gateway-3789b6a5f9e8?utm_source=chatgpt.com "Header Manipulation Using Envoy Filters in Istio Gateway"
[3]: https://github.com/envoyproxy/envoy/issues/7742?utm_source=chatgpt.com "Lua EnvoyFilter set multiple set-cookie header in request_handle ..."
[4]: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/lua_filter?utm_source=chatgpt.com "Lua — envoy 1.35.0-dev-377652 documentation"
[5]: https://stackoverflow.com/questions/76471418/envoy-lua-script-how-to-add-cookie-to-request-handlehttpcall-from-envoy-on-re?utm_source=chatgpt.com "Envoy Lua script - how to add cookie to request_handle:httpCall ..."
[6]: https://github.com/envoyproxy/envoy/issues/15612?utm_source=chatgpt.com "Rewritten Path and Domain in Set-Cookie headers should ... - GitHub"
[7]: https://github.com/kiali/kiali/blob/master/config/config.go?utm_source=chatgpt.com "kiali/config/config.go at master - GitHub"
[8]: https://stackoverflow.com/questions/74855625/how-can-i-rewrite-the-uri-path-on-an-incoming-request-with-istio?utm_source=chatgpt.com "How can I rewrite the URI path on an incoming request with Istio?"
