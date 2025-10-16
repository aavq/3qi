Похоже, Kiali не может достучаться до Jaeger Query и из-за этого «залипает» иконка загрузки. Ключевая подсказка — в логе видно URL без порта:
`http://simplest-query.jaeger` → это почти наверняка попытка сходить на порт **80**, тогда как Jaeger Query обычно слушает **16686 (HTTP API/UI)**. В результате — timeout и бесконечные ретраи, от которых в UI крутится спиннер.

Ниже — быстрый план «от простого к сложному».

# 1) Быстрая проверка из пода Kiali

```bash
# подставьте свой неймспейс с Kiali
KNS=kiali-system
kubectl -n $KNS get deploy kiali

# разовый curl из контейнера kiali на Jaeger Query (ожидаем JSON со списком сервисов)
kubectl -n $KNS exec deploy/kiali -c kiali -- sh -c \
  'apk add --no-cache curl >/dev/null 2>&1 || true; curl -sv --max-time 5 http://simplest-query.jaeger:16686/api/services'
```

* Если это вернуло JSON — сеть/ДНС в порядке, дело в **настройке URL** в Kiali.
* Если «Could not resolve host» — см. п.3 (ДНС/Service).
* Если timeout или connection refused — см. п.4 (NetworkPolicy / mTLS / порт).

# 2) Исправление конфигурации Kiali (самое вероятное)

## Вариант A: через Kiali CR (Operator)

Найдите CR:

```bash
kubectl get kiali -A
# допустим, CR называется "kiali" в ns kiali-system
kubectl -n kiali-system edit kiali kiali
```

Пропишите корректный Jaeger endpoint (обратите внимание на **:16686**):

```yaml
spec:
  external_services:
    tracing:
      enabled: true
      provider: jaeger
      in_cluster_url: "http://simplest-query.jaeger:16686"
      # опционально: публичный URL, чтобы ссылки из Kiali вели в UI Jaeger
      # url: "http://jaeger.your-domain.tld:16686"
      # если у вас gRPC в Jaeger не используется:
      use_grpc: false
```

Сохраните — оператор пересоберёт конфиг и перезапустит под.

## Вариант B: через Helm values (если ставили чартом kiali-server)

В values.yaml:

```yaml
external_services:
  tracing:
    enabled: true
    provider: jaeger
    in_cluster_url: "http://simplest-query.jaeger:16686"
    use_grpc: false
```

И примените `helm upgrade`.

> Почему это важно: без указания порта Kiali идёт на 80/tcp, а Service Jaeger обычно экспонирует только 16686 → соединение не устанавливается.

# 3) Убедиться, что Service существует и порт верный

```bash
kubectl -n jaeger get svc simplest-query -o yaml
```

Ищем порт **16686** (часто с именем `query-http`). Если сервиса нет или порт иной — поправьте URL или сам Service.

Проверка DNS-резолва из пода Kiali:

```bash
kubectl -n $KNS exec deploy/kiali -c kiali -- getent hosts simplest-query.jaeger || \
kubectl -n $KNS exec deploy/kiali -c kiali -- nslookup simplest-query.jaeger
```

# 4) Если порт/URL верные, но всё равно timeout

Чаще всего это одно из двух:

**(a) NetworkPolicy блокирует трафик**
Проверьте политики в `kiali-system` и `jaeger`. Разрешите egress из Kiali к Jaeger на 16686:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-kiali-to-jaeger
  namespace: jaeger
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: jaeger-query
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kiali-system
    ports:
    - protocol: TCP
      port: 16686
  policyTypes: [Ingress]
```

**(b) Istio mTLS STRICT в namespace `jaeger`**
Kiali — немешевый клиент и шлёт **plain HTTP**. При STRICT входящий не-mTLS трафик блокируется. Варианты решения:

* Быстро и просто — разрешить plaintext к Jaeger Query:

  ```yaml
  apiVersion: security.istio.io/v1beta1
  kind: PeerAuthentication
  metadata:
    name: jaeger-query-allow-plaintext
    namespace: jaeger
  spec:
    selector:
      matchLabels:
        app.kubernetes.io/name: jaeger-query
    mtls:
      mode: PERMISSIVE
  ```
* Либо **сделать Kiali «мешевым»** (включить sidecar в ns Kiali) и дать ему маршрут к Jaeger внутри меша (ServiceEntry/VirtualService/DestinationRule) — тогда трафик будет mTLS. Это чуть дольше, но «чище» в средах со STRICT.

# 5) Проверка здоровья Jaeger

```bash
kubectl -n jaeger get pods -owide
kubectl -n jaeger logs deploy/simplest-query --tail=200
# локально убедиться, что UI/HTTP жив:
kubectl -n jaeger port-forward svc/simplest-query 16686:16686
# затем в браузере: http://localhost:16686
```

# 6) Про «вечный» Loading Spinner в Kiali

Когда Kiali не может завершить health-проверки внешних сервисов (включая Jaeger), фронтенд периодически крутит спиннер рядом с логотипом.
**Временной костыль**, чтобы разблокировать UI, пока чините доступ к Jaeger:

```yaml
spec:
  external_services:
    tracing:
      enabled: false
```

Как только соединение к Jaeger наладите, верните `enabled: true`.

# 7) Быстрый чек-лист (TL;DR)

1. Поменять `in_cluster_url` на `http://simplest-query.jaeger:16686`.
2. Убедиться, что `svc/simplest-query` реально слушает **16686**.
3. Проверить резолв/доступ из пода Kiali (`curl ...:16686/api/services`).
4. Если таймаут — посмотреть NetworkPolicy и Istio mTLS (STRICT → PERMISSIVE для jaeger-query или «включить» Kiali в mesh).
5. Перезапустить/подождать reconciler Kiali и убедиться, что спиннер пропал.

Если пришлёте:

* вывод `kubectl -n kiali-system get kiali -o yaml` (или values/ConfigMap),
* `kubectl -n jaeger get svc simplest-query -o yaml`,
* и 10–15 строк логов из `deploy/kiali` вокруг ошибки,

— я смогу точечно указать, где именно «стрелка» и дать готовые патчи под ваш вариант (Operator/Helm).
