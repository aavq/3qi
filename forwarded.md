## Коротко — что нужно сделать

У Kiali за «правильный» URL отвечают заголовки `X-Forwarded-Proto`, `X-Forwarded-Port` и (реже) `X-Forwarded-Host`. Когда их нет, Kiali собирает callback-адрес из внутренних параметров пода (`https://…:20001`) и браузер уходит в тайм-аут. Решение — заставить Istio IngressGateway/VirtualService прописывать эти заголовки при форвардинге запросов на сервис **kiali** — и проблема с переадресацией исчезает. ([github.com][1], [kiali.io][2])

---

## 1 Пререквизиты

* Kiali развёрнут как сервис `kiali` в неймспейсе `kiali`, порт `20001` (дефолт у Helm/Operator).
* У вас уже установлен Istio IngressGateway (`istio-ingressgateway`) и DNS-имя `kiali.intranet.corp.com` указывает на его LB.
* TLS терминируется на IngressGateway (порт 443).

---

## 2 Gateway — принимаем HTTPS

```yaml
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: kiali-gw
  namespace: istio-system      # можно в любом ns, лишь бы видел ingressgateway
spec:
  selector:
    istio: ingressgateway      # стандартная метка подов Gateway
  servers:
  - port:
      number: 443
      name: https
      protocol: HTTPS
    hosts:
    - kiali.intranet.corp.com
    tls:
      mode: SIMPLE             # TLS-терминация на gateway
      credentialName: kiali-cert   # секрет с cert/key в istio-system
```

Gateway описывает публичное соединение, но **не** меняет заголовки — это сделает VirtualService. ([istio.io][3])

---

## 3 VirtualService — прописываем `X-Forwarded-*`

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: kiali-vs
  namespace: istio-system
spec:
  gateways:
  - kiali-gw                    # привязка к Gateway
  hosts:
  - kiali.intranet.corp.com     # то же FQDN, что в Gateway
  http:
  - match:                      # один маршрут на все пути /kiali
    - uri: { prefix: /kiali }
    headers:
      request:
        set:                    # 👉 ключевой раздел!
          X-Forwarded-Proto: "https"
          X-Forwarded-Port:  "443"
          X-Forwarded-Host:  "kiali.intranet.corp.com"
    rewrite:                    # (необязательно) убираем двойной /kiali/kiali
      uri: /kiali
    route:
    - destination:
        host: kiali.kiali.svc.cluster.local
        port: { number: 20001 }
```

* Поле `headers.request.set` официально поддерживается в `VirtualService` и позволяет добавить/перезаписать любые заголовки ([istio.io][4], [istio.io][5]).
* Здесь мы явно сообщаем Kiali, что пользователь пришёл по `https://…:443`; Kiali больше не будет подставлять порт 20001 в redirect.
* Аналогичный пример приводят сами разработчики Kiali в FAQ → «How to configure the originating port…» ([kiali.io][2]).

> **Почему VirtualService, а не Gateway/EnvoyFilter?**
>
> * В Gateway есть поле `requestHeadersToAdd`, но оно применяется *до* SNI-роутинга и не всегда удобно; а в VirtualService мы можем дать разные заголовки для разных маршрутов. ([github.com][6], [stackoverflow.com][7])

---

## 4 Применяем и проверяем

```bash
kubectl apply -f gateway-kiali.yaml
kubectl apply -f virtualservice-kiali.yaml
```

### Проверка cURL-ом

```bash
curl -Ik https://kiali.intranet.corp.com/kiali/api
```

* В ответном `Location` после клика «Login with OpenID» **не** должно быть `:20001`.
* Логи пода Kiali (`kubectl logs deploy/kiali -n kiali | grep X-Forwarded`) покажут полученные заголовки.

---

## 5 Частые вопросы

| Симптом                                 | Причина                                                       | Решение                                                                          |
| --------------------------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| В redirect всё ещё `:20001`             | Заголовки не пришли до Kiali                                  | Убедитесь, что VirtualService сматчился (смотрим `istioctl proxy-config routes`) |
| В IdP «redirect\_uri mismatch»          | TLS терминируется *за* Istio и URL меняется                   | Укажите тот же `redirect_uri` в Kiali CR и в регистрации клиента IdP             |
| Нужен и `X-Forwarded-For` (реальный IP) | За Istio ещё один LB                                          | Настройте `numTrustedProxies` в GatewayTopology или EnvoyFilter ([istio.io][8])  |
| Приложение работает по HTTP             | Поставьте `X-Forwarded-Proto: "http"` и уберите TLS в Gateway |                                                                                  |

---

## 6 Если хочется через EnvoyFilter (альтернатива)

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: kiali-forwarded
  namespace: istio-system
spec:
  workloadSelector:
    labels: { istio: ingressgateway }
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      listener: { portNumber: 443, filterChain: { filter: { name: "envoy.filters.network.http_connection_manager" } } }
    patch:
      operation: MERGE
      value:
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
          request_headers_to_add:
          - header: { key: "X-Forwarded-Proto", value: "https" }
          - header: { key: "X-Forwarded-Port",  value: "443" }
```

Но в 99 % случаев достаточно VirtualService; EnvoyFilter сложнее поддерживать. ([github.com][9])

---

## 7 Итого

1. Gateway публикует `kiali.intranet.corp.com:443` и заверяет TLS.
2. VirtualService при проксировании *добавляет* `X-Forwarded-Proto/Port/Host`.
3. Kiali видит внешние параметры запроса и формирует корректный `redirect_uri` без порта 20001.

После применения этих YAML-ов кнопка «Login with OpenID» должна без ошибок возвращать вас в Web-UI уже под авторизованной сессией. Если что-то пойдёт не так — проверяйте, что заголовки реально присутствуют в запросе, используя `istioctl pc log` или обычный `tcpdump`. ([stackoverflow.com][10], [kiali.io][11], [istio.io][12])

[1]: https://github.com/kiali/kiali/issues/3111?utm_source=chatgpt.com "Add configuration option to specify Kiali's public port (OIDC support)"
[2]: https://kiali.io/docs/faq/authentication/ "Authentication | Kiali"
[3]: https://istio.io/latest/docs/reference/config/networking/gateway/?utm_source=chatgpt.com "Istio / Gateway"
[4]: https://istio.io/latest/docs/reference/config/networking/virtual-service/?utm_source=chatgpt.com "Istio / Virtual Service"
[5]: https://istio.io/latest/docs/reference/config/networking/virtual-service/ "Istio / Virtual Service"
[6]: https://github.com/istio/istio/issues/7964?utm_source=chatgpt.com "Istio give x-forwarded-proto=http to upstream server when using SSL ..."
[7]: https://stackoverflow.com/questions/66314276/how-to-remove-or-modify-header-from-istio-ingress-gateway?utm_source=chatgpt.com "How to remove or modify header from istio ingress gateway"
[8]: https://istio.io/latest/docs/ops/configuration/traffic-management/network-topologies/?utm_source=chatgpt.com "Configuring Gateway Network Topology - Istio"
[9]: https://github.com/envoyproxy/envoy/issues/3732?utm_source=chatgpt.com "Add X-Forwarded-Port header · Issue #3732 · envoyproxy/envoy"
[10]: https://stackoverflow.com/questions/76635291/include-x-forwarded-port-header-on-requests-through-an-istio-proxy?utm_source=chatgpt.com "Include X-Forwarded-Port header on requests through an Istio proxy"
[11]: https://kiali.io/docs/faq/authentication/?utm_source=chatgpt.com "Authentication - Kiali"
[12]: https://istio.io/latest/blog/2020/show-source-ip/?utm_source=chatgpt.com "Proxy protocol on AWS NLB and Istio ingress gateway"
