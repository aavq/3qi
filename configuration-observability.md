### Что вообще происходит, когда вы пишете

```yaml
headers:
  request:
    set:
      x‑client‑subject: "%DOWNSTREAM_PEER_SUBJECT%"
```

| Шаг | Что делает Envoy/ Istio | Детали |
|-----|------------------------|--------|
| **1. TLS‑рукопожатие** | Gateway (или сайдкар) принимает mTLS‑соединение и достаёт **сертификат клиента**. |
| **2. Запуск HTTP‑маршрута** | Попадаем в выбранный `VirtualService` → секция `http[ … ]`. |
| **3. Заголовочная операция** | Поле `headers.request.set` говорит: *«перед тем, как отправить запрос upstream, установи/перезапиши заголовок* `x‑client‑subject`». |
| **4. Подстановка переменной** | В значении стоит **формат‑строка** Envoy `%DOWNSTREAM_PEER_SUBJECT%`. При обработке она **заменяется** на Subject клиентского сертификата, например<br>`CN=alice,O=Corp,C=DE`.citeturn13view0 |
| **5. Передача дальше** | Готовый заголовок едет во все последующие прокси и в само приложение. |

Ключевые факты
--------------

1. **Формат‑строки Envoy.**  
   Envoy разрешает использовать *любые* «command‑operator’ы», которые он применяет в access‑логах, и в заголовках — док прямо это говорит.citeturn12view0  
   Поэтому `%DOWNSTREAM_PEER_SUBJECT%`, `%DOWNSTREAM_PEER_URI_SAN%`, `%HOSTNAME%`, `%TRACE_ID%` и десятки других переменных работают «как есть».

2. **Работает только после успешного mTLS.**  
   Если клиент не предъявил сертификат (или Gateway в режиме `SIMPLE`), переменная раскроется в `-` (пустую строку).

3. **`set` vs `add`.**  
   * `set:` — стирает существующий `x‑client‑subject` и пишет новое значение.  
   * `add:` — добавит **второе** значение, если такой заголовок уже был (что редко нужно для идентификаторов).

4. **Без Lua/EnvoyFilter.**  
   Всё делается штатными CRD Istio — проще сопровождать, не ломается при апгрейдах.

Минимальный рабочий пример
--------------------------

```yaml
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: mtls-gw
spec:
  selector:
    istio: ingressgateway
  servers:
  - port: { number: 443, name: https, protocol: HTTPS }
    hosts: ["stack17.app.example.internal"]
    tls:
      mode: MUTUAL
      credentialName: stack17-cred     # секрет с серверным crt/key и CA

---
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: stack17-vs
spec:
  hosts: ["stack17.app.example.internal"]
  gateways: ["mtls-gw"]
  http:
  - name: to-backend
    headers:
      request:
        set:
          x-client-subject: "%DOWNSTREAM_PEER_SUBJECT%"
    route:
    - destination:
        host: stack17-backend.uat.svc.cluster.local
        port: { number: 8443 }
```

После деплоя:

```bash
curl --cert client.pem --key client.key --cacert ca.pem \
     https://stack17.app.example.internal/ -v \
     | grep x-client-subject
# ⇒ x-client-subject: CN=alice,O=Corp,C=DE
```

Как получить **только CN**, а не всю строку
------------------------------------------

* **На стороне приложения** — сплит по `,`, найдите подстроку, начинающуюся с `CN=`.  
* **На стороне прокси** — придётся Lua или Wasm: возьмите `%DOWNSTREAM_PEER_SUBJECT%` в заголовок, затем `header_to_metadata` + regex `((?<=CN=)[^,]+)`.

Другие полезные переменные
--------------------------

| Переменная | Что возвращает |
|------------|----------------|
| `%DOWNSTREAM_PEER_URI_SAN%` | Первый URI SAN (полезно для SPIFFE) |
| `%DOWNSTREAM_TLS_VERSION%`  | `TLSv1.2` / `TLSv1.3` |
| `%DOWNSTREAM_REMOTE_ADDRESS%` | IP клиента |
| `%REQUEST_ID%` | Тот же UUID, что идёт в `x-request-id` |

Проверка и защита
-----------------

* **Логи.** Добавьте в формат access‑лога `%REQ(x-client-subject)%` — сразу увидите, что значение приезжает.  
* **Без спуфинга.** Использование `set:` гарантирует, что внешние клиенты не смогут подделать заголовок — шлюз перезапишет его.

---

**Итого:** строка

```yaml
x-client-subject: "%DOWNSTREAM_PEER_SUBJECT%"
```

— это самый короткий, поддерживаемый и «родной» для Istio/Envoy способ протащить поле *Subject* (а через него и CN) клиентского сертификата дальше по цепочке без кастомных фильтров и скриптов.




***
***
***


Ниже ― «шпаргалка» по **всем** командным‑операторам (format‑string variables) Envoy 1.35 — именно эти строки вы можете ставить в `headers.request.set`, `access_log.format`, `FaultAbort.header_format` и т.д.  

> Если искомое значение отсутствует, Envoy запишет `-`. Любой оператор можно обернуть в `(...)` для обрезки (`%START_TIME(%s)%`, `%REQ(User-Agent):20%`) или дополнить параметрами, как `%REQ(X?Y):Z%`. citeturn1view0  

---

### 1. Временные метки  
`%START_TIME%`, `%START_TIME_LOCAL%`, `%EMIT_TIME%`, `%EMIT_TIME_LOCAL%`, `%COMMON_DURATION(…)%`, `%REQUEST_DURATION%`, `%RESPONSE_DURATION%`, `%REQUEST_TX_DURATION%`, `%RESPONSE_TX_DURATION%`, `%ROUNDTRIP_DURATION%`, `%DOWNSTREAM_HANDSHAKE_DURATION%`, `%UPSTREAM_CONNECTION_POOL_READY_DURATION%` citeturn1view0turn4view0  

### 2. Счётчики байт/пакетов  
`%REQUEST_HEADERS_BYTES%`, `%RESPONSE_HEADERS_BYTES%`, `%RESPONSE_TRAILERS_BYTES%`, `%BYTES_RECEIVED%`, `%BYTES_SENT%`, `%BYTES_RETRANSMITTED%`, `%PACKETS_RETRANSMITTED%`, `%UPSTREAM_WIRE_BYTES_SENT%`, `%UPSTREAM_WIRE_BYTES_RECEIVED%`, `%DOWNSTREAM_WIRE_BYTES_SENT%`, `%DOWNSTREAM_WIRE_BYTES_RECEIVED%`, `%UPSTREAM_HEADER_BYTES_SENT%`, `%UPSTREAM_HEADER_BYTES_RECEIVED%`, `%DOWNSTREAM_HEADER_BYTES_SENT%`, `%DOWNSTREAM_HEADER_BYTES_RECEIVED%` citeturn1view0  

### 3. Протокол, коды и флаги  
`%PROTOCOL%`, `%UPSTREAM_PROTOCOL%`, `%RESPONSE_CODE%`, `%RESPONSE_CODE_DETAILS%`, `%RESPONSE_FLAGS%`, `%RESPONSE_FLAGS_LONG%`, `%GRPC_STATUS%`, `%GRPC_STATUS_NUMBER%` citeturn4view0  

### 4. Уникальные идентификаторы  
`%TRACE_ID%`, `%UNIQUE_ID%`, `%CONNECTION_ID%`, `%UPSTREAM_CONNECTION_ID%`, `%STREAM_ID%`, `%REQUEST_ID%` (как `%REQ(X‑REQUEST‑ID)%`) citeturn3view0turn5view0  

### 5. Адреса и порты  

| Downstream | Upstream |
|------------|----------|
| `%DOWNSTREAM_REMOTE_ADDRESS%`, `_WITHOUT_PORT%`, `%DOWNSTREAM_REMOTE_PORT%`, `%DOWNSTREAM_DIRECT_REMOTE_*%` | `%UPSTREAM_REMOTE_ADDRESS%`, `_WITHOUT_PORT%`, `%UPSTREAM_REMOTE_PORT%` |
| `%DOWNSTREAM_LOCAL_ADDRESS%`, `%DOWNSTREAM_LOCAL_PORT%`, `%DOWNSTREAM_DIRECT_LOCAL_*%` | `%UPSTREAM_LOCAL_ADDRESS%`, `%UPSTREAM_LOCAL_PORT%` |  

Плюс `%DOWNSTREAM_TRANSPORT_FAILURE_REASON%`, `%UPSTREAM_TRANSPORT_FAILURE_REASON%` citeturn3view0  

### 6. TLS / X.509 клиента (downstream)  
`%DOWNSTREAM_PEER_SUBJECT%`, `%DOWNSTREAM_PEER_URI_SAN%`, `%DOWNSTREAM_PEER_DNS_SAN%`, `%DOWNSTREAM_PEER_IP_SAN%`, `%DOWNSTREAM_TLS_SESSION_ID%`, `%DOWNSTREAM_TLS_CIPHER%`, `%DOWNSTREAM_TLS_VERSION%`, `%DOWNSTREAM_PEER_CERT%`, `%DOWNSTREAM_PEER_CERT_V_START%`, `%DOWNSTREAM_PEER_CERT_V_END%`, `%TLS_JA3_FINGERPRINT%` citeturn2view0  

### 7. TLS сервера (upstream)  
Аналогичный набор с префиксом **`%UPSTREAM_…`**: `%UPSTREAM_PEER_SUBJECT%`, `%UPSTREAM_PEER_URI_SAN%`, `%UPSTREAM_PEER_ISSUER%`, `%UPSTREAM_TLS_VERSION%`, `%UPSTREAM_PEER_CERT%`, `%UPSTREAM_PEER_CERT_V_START%`, `%UPSTREAM_PEER_CERT_V_END%` citeturn2view0  

### 8. Маршрутизация и логика xDS  
`%ROUTE_NAME%`, `%VIRTUAL_CLUSTER_NAME%`, `%UPSTREAM_CLUSTER%`, `%UPSTREAM_CLUSTER_RAW%`, `%UPSTREAM_HOST%`, `%UPSTREAM_HOST_NAME%`, `%UPSTREAM_HOST_NAME_WITHOUT_PORT%`, `%FILTER_CHAIN_NAME%`, `%ACCESS_LOG_TYPE%` citeturn4view0turn5view0  

### 9. Заголовки, трейлеры, cookies, query‑параметры  
* `%REQ(Hdr?Alt):Z%` — запрос‑header  
* `%RESP(Hdr):Z%` — ответ  
* `%TRAILER(Hdr)%` — трейлеры  
* `%COOKIES(CookieName)%` (если включён cookie‑formatter)  
* `%QUERY_PARAM(key):Z%`, `%PATH(WQ|NQ:ORIG|PATH):Z%`, `%HOSTNAME%` citeturn3view0  

### 10. Метаданные, фильтр‑state, env  
* `%DYNAMIC_METADATA(ns:key)%` (устаревший; лучше `%METADATA%`)  
* `%CLUSTER_METADATA(ns:key)%`, `%UPSTREAM_METADATA(ns:key)%`  
* `%FILTER_STATE(Key[:PLAIN|TYPED|FIELD])%`  
* `%METADATA(type:ns:key)%` (единый оператор новых версий)  
* `%ENVIRONMENT(VAR):Z%` citeturn3view0  

### 11. Другое полезное  
`%CUSTOM_FLAGS%` (произвольные флаги), `%REQUEST_HEADERS_BYTES%`, `%PACKETS_RETRANSMITTED%`, `%DOWNSTREAM_WIRE_BYTES_SENT%` и любые новые операторы, добавляемые в будущих релизах. Проверяйте changelog Envoy. citeturn1view0  

---

#### Универсальные шаблоны

* **Любой запрос‑хедер:** `%REQ(Header-Name)%`  
* **Любой ответ‑хедер:** `%RESP(Header-Name)%`  
* **Трейлер:** `%TRAILER(Header)%`  
* **Строка Subject полностью:** `%DOWNSTREAM_PEER_SUBJECT%`  
* **Только CN разбираем в сервисе** (или Lua/Wasm фильтром).  

Эти же переменные можно ставить в **Gateway** → `headers.request.set`, чтобы после mTLS‑терминации записывать их в HTTP‑заголовки. Например:

```yaml
headers:
  request:
    set:
      x-client-subject: "%DOWNSTREAM_PEER_SUBJECT%"
      x-trace-id:       "%TRACE_ID%"
```

Теперь приложение получает проверенные данные о сертификате и трассировке «из коробки».


https://www.envoyproxy.io/docs/envoy/latest/configuration/observability/access_log/usage




