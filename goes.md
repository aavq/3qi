Ниже разбор каждого «жёлтого/красного» сообщения из лога Kiali 2.15 и что с этим делать. Я даю: причина → что проверить/как исправить (с примерами Helm-values/CR).

⸻

1) DEPRECATION NOTICE: 'external_services.tracing.in_cluster_url' ... → 'external_services.tracing.internal_url'

2) DEPRECATION NOTICE: 'external_services.tracing.url' ... → 'external_services.tracing.external_url'

Причина. В 2.15 переименованы ключи конфигурации Jaeger/Tracing. Старые читаются, но помечены как deprecated.

Как исправить. В values/CR замените ключи:

Было (≤2.14):

external_services:
  tracing:
    url: https://jaeger.example.com          # внешний URL (для ссылок из UI)
    in_cluster_url: http://simplest-query.jaeger:16686  # внутренний URL (HTTP)

Стало (2.15+):

external_services:
  tracing:
    provider: jaeger
    external_url: https://jaeger.example.com
    internal_url: http://simplest-query.jaeger:16686

Если используете gRPC к Jaeger, дополнительно:

external_services:
  tracing:
    use_grpc: true
    grpc_address: simplest-query.jaeger:16685


⸻

3) Using authentication strategy [anonymous]

4) Kiali auth strategy is configured for anonymous access – users will not be authenticated.

Причина. Включена стратегия anonymous. Это не ошибка, но предупреждение о том, что любой получит доступ к UI.

Как исправить (если нужен логин).
	•	Простейший вариант — token.
	•	Корпоративный — openid (OIDC/Keycloak/…).

Пример (OIDC):

auth:
  strategy: openid
  openid:
    issuer_uri: https://auth.example.com/realms/my
    client_id: kiali
    client_secret: <secret>
    scopes: ["openid","profile","email"]


⸻

5) Some validation errors will be ignored [KIA1301]

Причина. Kiali загрузил список игнорируемых валидаторов (feature-flag). Это сделано, чтобы убрать шум известных «ложных срабатываний».

Что проверить.
	•	В ConfigMap/values есть блок:

kiali_feature_flags:
  validations:
    ignore:
      - KIAxxxx
      - KIAyyyy


	•	Если вы это не настраивали — в 2.15 такой список мог прийти дефолтом чартом/оператором.

Как изменить.
	•	Удалите/сузьте список ignore, если хотите видеть все валидации:

kiali_feature_flags:
  validations:
    ignore: []



⸻

6) Kiali: Version: unknown, Commit: unknown, Go: unknown

Причина. Образ Kiali собран/вытянут без «вшитых» метаданных (часто это :latest/dev-сборка, кастомный ребилд, или сторонний mirror).

Как исправить.
	•	Зафиксируйте официальный тег версии:

image:
  repo: quay.io/kiali/kiali
  tag: v2.15.0   # или ваш точный релиз
  pullPolicy: IfNotPresent


	•	Перекатите deployment. После этого в логе появится реальная версия/коммит/Go.

⸻

7) Create [jaeger] GRPC client. address=[simplest-query.jaeger:16685]

8) jaeger version check failed ... context deadline exceeded

9) jaeger version check failed ... code=[503]

Что это значит.
Kiali пытается:
	1.	Подключиться к Jaeger по gRPC (порт 16685) — строка Create [jaeger] GRPC client….
	2.	Проверить версию Jaeger по HTTP (использует internal_url) — и тут фейлы: таймаут/503.

Типовые причины и решения (идём сверху вниз):
	1.	Неверный internal_url (без порта).
В логе видно, что Kiali ходит на http://simplest-query.jaeger без :16686.
	•	Решение: допишите порт HTTP UI Jaeger:

external_services:
  tracing:
    internal_url: http://simplest-query.jaeger:16686


	•	Быстрый тест из пода Kiali:

kubectl -n <ns-kiali> exec -it deploy/kiali -- sh
wget -S -O- http://simplest-query.jaeger:16686


	2.	Сервис/порт Jaeger не совпадает.
	•	Проверьте Service:

kubectl -n jaeger get svc simplest-query -o yaml | egrep 'ports:|name:|port:|targetPort:'


	•	Должны быть:
	•	16686 (HTTP UI / API)
	•	по необходимости 16685 (gRPC).

	3.	NetworkPolicy блокирует трафик от Kiali → Jaeger.
	•	В jaeger namespace может быть политика, запрещающая ingress со стороны kiali ns.
	•	Решение (пример разрешения):

apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-kiali-to-jaeger
  namespace: jaeger
spec:
  podSelector: {}   # или по лейблам query/collector
  policyTypes: ["Ingress"]
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kiali


	4.	Istio mTLS STRICT у Jaeger, а Kiali — без сайдкара.
В этом случае HTTP/gRPC снаружи меша вернёт 503.
Варианты:
	•	Проще: отключить sidecar-инъекцию у Jaeger:

kubectl label ns jaeger istio-injection-
# перезапустить поды Jaeger


	•	Или ослабить PeerAuthentication:

apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: allow-plain
  namespace: jaeger
spec:
  mtls:
    mode: PERMISSIVE


	•	Или инжектить сайдкар в Kiali (реже рекомендуется):

kubectl -n kiali patch deploy kiali \
  -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"true"}}}}}'


	5.	Сам Jaeger не жив/не готов.
	•	Посмотрите kubectl -n jaeger get pods, логи *-query, readiness.
	•	Проверьте напрямую:

kubectl -n jaeger port-forward svc/simplest-query 16686:16686
curl -I http://localhost:16686


	6.	gRPC-часть (16685) выключена/недоступна.
	•	Если не пользуетесь gRPC, просто отключите:

external_services:
  tracing:
    use_grpc: false


	•	Если пользуетесь — проверьте доступность:

# при наличии grpcurl
grpcurl -plaintext simplest-query.jaeger:16685 list



⸻

10) Tracing Enabled. Initializing tracer with collector url: simplest-collector.jaeger:4317

Причина. Сам Kiali отправляет свои спаны в Jaeger Collector по OTLP gRPC :4317. Это информационное сообщение.

Что проверить.
Если не хотите, отключите:

server:
  tracing:
    enabled: false

Или убедитесь, что simplest-collector.jaeger:4317 доступен (NetworkPolicy / mTLS см. выше).

⸻

Короткий чек-лист «починить быстро»
	1.	Переименовать ключи: in_cluster_url→internal_url, url→external_url.
	2.	Указать порт в internal_url: http://simplest-query.jaeger:16686.
	3.	Если используете gRPC — включить use_grpc и grpc_address: ...:16685, иначе отключить use_grpc.
	4.	Auth: оставить anonymous (если так задумано) или переключиться на openid/token.
	5.	Версия unknown: зафиксировать официальный тег образа quay.io/kiali/kiali:v2.15.x.
	6.	NetworkPolicy/mTLS: убедиться, что из kiali ns есть доступ к Jaeger, и что mTLS не мешает (PERMISSIVE/без сайдкара/инжекция в Kiali — выбрать один путь).
	7.	Validations ignore: при необходимости очистить список kiali_feature_flags.validations.ignore.

Если хочешь — пришли свой актуальный values.yaml/CR для Kiali и kubectl -n jaeger get svc simplest-query -o yaml. Я сверю поля/порты и дам точные поправки под твою установку.
