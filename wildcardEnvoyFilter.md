**Коротко:**
Чтобы `envoy.filters.http.oauth2` автоматически включался для всех доменов вида `*.cluster.httpbin.lima`, достаточно (1) создать/изменить `Gateway`, у которого в поле `hosts` указан точно такой же шаблон, и (2) в `EnvoyFilter` заменить `sni: "httpbin.lima"` на `sni: "*.cluster.httpbin.lima"`. В Envoy/Istio это не “маска” или regex, а строка, совпадающая с `server_names` той же filter-chain; wild-card (`*.`) работает на уровне самого Envoy и охватывает все поддомены первого уровня([envoyproxy.io][1], [github.com][2]). Ниже—подробности, готовые YAML-примеры и подводные камни.

---

## 1. Как Envoy и Istio матчат SNI-хосты

| Факт                                                                                                                                         | Где зафиксировано     |
| -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| `server_names` в FilterChain допускает единственный `*` только в левом компоненте (`*.example.com`)([envoyproxy.io][1], [github.com][2])     | Envoy API             |
| При TLS-рукопожатии Envoy сначала ищет полное имя, потом `*.example.com`, потом `*.com`([envoyproxy.io][3])                                  | Envoy API             |
| В Istio `Gateway.spec.servers[].hosts` тоже принимает wildcard в левом компоненте FQDN([istio.io][4])                                        | Istio Gateway API     |
| `EnvoyFilter.match.listener.filterChain.sni`—это **строгое** сравнение с конфигурацией FilterChain, не regex([istio.io][5], [github.com][6]) | Istio EnvoyFilter doc |
| Если вы уберёте поле `sni`, патч применится ко всем FilterChain на порту — будьте осторожны ([github.com][6])                                | GitHub discussion     |
| Wildcard-SNI также фигурирует в TLS-matchах VirtualService и AuthorizationPolicy (ключ `connection.sni`)([pub.dev][7], [istio.io][8])        | Istio API             |

## 2. Шаг 1 — описываем Gateway с wildcard-host

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: Gateway
metadata:
  name: httpbin-wildcard
  namespace: istio-system
spec:
  selector:
    istio: ingressgateway
  servers:
  - port:
      number: 8443
      name: https
      protocol: HTTPS
    tls:
      mode: SIMPLE                 # или MUTUAL, mTLS — как у вас
      credentialName: httpbin-wildcard-cert   # секрет с SAN = *.cluster.httpbin.lima
    hosts:
    - "*.cluster.httpbin.lima"
```

*Пояснение*: поле `hosts` в Gateway **должно** содержать ту же строку (`*.cluster.httpbin.lima`), потому что именно на её основе Istio создаёт FilterChain с `server_names: ["*.cluster.httpbin.lima"]`([istio.io][4]).

## 3. Шаг 2 — патчим EnvoyFilter под wildcard SNI

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: httpbin-oauth-gw-wildcard
  namespace: istio-system
spec:
  priority: 10
  workloadSelector:
    labels:
      istio: ingressgateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
      listener:
        portNumber: 8443
        filterChain:
          sni: "*.cluster.httpbin.lima"          # ← ключевая строка
          filter:
            name: envoy.filters.network.http_connection_manager
            subFilter:
              name: envoy.filters.http.router
    patch:
      operation: INSERT_FIRST
      value:
        name: envoy.filters.http.oauth2
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
          # остальная конфигурация – без изменений …
```

### На что обратить внимание

1. **Кавычки** вокруг `*.cluster.httpbin.lima` обязательны, чтобы YAML не считал `*` спец-символом.
2. Если нужно охватить несколько разных wildcard-зон (напр. `*.foo.lima` и `*.bar.lima`), создайте несколько `configPatches` с разными `sni`.
3. Убедитесь, что tls-сертификат (`credentialName`) содержит SAN = `*.cluster.httpbin.lima`; иначе браузер покажет warning.
4. При HTTP/2 reuse нескольких wildcard-серверов возможно «залипание» соединения на неподходящем `VirtualHost`, что ведёт к 404; Istio разбиралось с дубликатами filter-chain match ([github.com][9]).

## 4. Проверка

```bash
# увидим цепочку с  server_names: ["*.cluster.httpbin.lima"]
istioctl proxy-config listener <ingress-pod> -n istio-system --port 8443 -o json | jq '.dynamic_listeners[].active_state.listener.filter_chains[].filter_chain_match'
```

Патч должен появиться сразу за `tls_inspector`-фильтром:

```bash
istioctl proxy-config filter <ingress-pod> -n istio-system --name envoy.filters.http.oauth2
```

## 5. Альтернативы

| Подход                                                              | Когда полезен                                                                                        |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Убрать поле `sni`** и патчить весь 8443-порт                      | Если на шлюзе ВСЕ хосты требуют OAuth2. Самый простой, но неточно таргетирует ([github.com][6])      |
| **Использовать `routeConfiguration.vhost.domainName`** вместо `sni` | Если TLS терминируется *другим* шлюзом (L7-ограничение) — см. `applyTo: VIRTUAL_HOST`([istio.io][5]) |
| **AuthorizationPolicy c `connection.sni`**                          | Для логики «только выпусти 302 на login для доменов *X*» без EnvoyFilter                             |
| **Отдельный Gateway**                                               | Когда нужен разный OAuth-провайдер для разных wildcard-зон                                           |

## 6. Отладка и обновления

* Обновитесь минимум до Istio ≥ 1.20 — там фиксы по дубликатам wildcard-listener’ов и более надёжный `oauth2`-фильтр([istio.io][10]).
* Для сложных случаев смотрите готовый патч-пример в документации (`hcm-tweaks`) — схожая структура, только с OAuth вместо HCM MERGE([istio.io][11]).
* `istioctl x envoy-config` полезен для live-диагностики того, что Istio реально сгенерировал.

---

### Что дальше?

Если нужно покрыть ещё более общие зоны (например, все `*.lima`) или хотите комбинировать несколько OAuth-конфигураций через один шлюз — дайте знать, покажу подход с несколькими Listener’ами и переключением по ALPN/SNI.

[1]: https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/listener/v3/listener_components.proto?utm_source=chatgpt.com "Listener components (proto) - Envoy proxy"
[2]: https://github.com/envoyproxy/envoy/issues/3363?utm_source=chatgpt.com "Clarification of wildcards in sniDomains of filterChainMatch #3363"
[3]: https://www.envoyproxy.io/docs/envoy/latest/xds/type/matcher/v3/domain.proto?utm_source=chatgpt.com "Server name matcher (proto) - Envoy proxy"
[4]: https://istio.io/latest/docs/reference/config/networking/gateway/?utm_source=chatgpt.com "Istio / Gateway"
[5]: https://istio.io/latest/docs/reference/config/networking/envoy-filter/?utm_source=chatgpt.com "Envoy Filter - Istio"
[6]: https://github.com/istio/istio/discussions/49324?utm_source=chatgpt.com "Can not apply EnvoyFilter to specific domain #49324 - GitHub"
[7]: https://pub.dev/documentation/kubernetes/latest/io.istio.v1beta1/TLSMatchAttributes-class.html "TLSMatchAttributes class - io.istio.v1beta1 library - Dart API"
[8]: https://istio.io/latest/docs/reference/config/security/conditions/?utm_source=chatgpt.com "Authorization Policy Conditions - Istio"
[9]: https://github.com/istio/istio/issues/16573?utm_source=chatgpt.com "Gateway with wildcard hosts for different namespaces causes ..."
[10]: https://istio.io/latest/blog/2023/egress-sni/?utm_source=chatgpt.com "Routing egress traffic to wildcard destinations - Istio"
[11]: https://istio.io/latest/docs/reference/config/networking/envoy-filter/ "Istio / Envoy Filter"
