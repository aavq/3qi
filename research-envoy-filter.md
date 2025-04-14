***
***
***

# Мне нужно достичь уровня эксперт в знаниях EnvoyFilter. Составь подробный план того что нужно знать


***
***
***

Чтобы достичь экспертного уровня в работе с **EnvoyFilter** (ключевой компонент в Istio для глубокой кастомизации прокси-поведения), нужно охватить как фундаментальные знания, так и продвинутые темы. Ниже — **структурированный и подробный план**, разбитый по уровням:

---

### **I. Базовые знания (основа Envoy)**
Перед тем как глубоко работать с `EnvoyFilter`, нужно хорошо понимать сам **Envoy Proxy**:
#### 1. Архитектура Envoy
- Основные понятия: Listener, Cluster, Route, Filter Chain, Endpoint
- Event loop и worker threads
- Bootstrap-конфигурация и hot restart

#### 2. Конфигурация Envoy
- Формат конфигурации (JSON/YAML)
- Статическая и динамическая конфигурация (xDS-протоколы)
- ADS (Aggregated Discovery Service)

#### 3. Понимание фильтров
- Network filters (TCP, TLS Inspector, etc.)
- HTTP filters (Router, JWT, Rate Limit, Lua, Wasm)

---

### **II. Envoy в контексте Istio**
#### 1. Архитектура Istio
- Envoy как Data Plane
- Istiod как Control Plane
- Принцип sidecar injection

#### 2. VirtualService и DestinationRule
- Как они конфигурируют поведение Envoy-прокси
- Match / Route / Retry / Timeout / Header manipulation

---

### **III. EnvoyFilter: Общее понимание**
#### 1. Назначение ресурса `EnvoyFilter`
- Возможности: модификация listener/cluster/route/final filters
- Ограничения и риски (нестабильность при обновлении Istio)

#### 2. Структура ресурса EnvoyFilter
- `workloadSelector`
- `configPatches`
  - `applyTo`: (e.g., HTTP_FILTER, NETWORK_FILTER, CLUSTER, etc.)
  - `match`: (listener/route/cluster/...)
  - `patch`: operation (MERGE, ADD, REMOVE)

#### 3. Типовые сценарии
- Добавление кастомного HTTP фильтра
- Инжекция Lua-скрипта
- Перехват/изменение заголовков
- Редиректы и response rewriting

---

### **IV. Практика и кейсы**
#### 1. Lua-фильтры
- Основы Lua в Envoy
- Примеры: логирование, JWT-декодинг, редиректы

#### 2. Wasm-фильтры
- WebAssembly-фильтры: как писать, билдить, деплоить
- Инструменты: Proxy-Wasm SDK (Rust/Go/C++)
- Пример: авторизация, трейсинг, метрики

#### 3. Match-условия
- Поиск нужного listener/route/cluster
- Отладка: `istioctl proxy-config` и `istioctl pc routes/listeners`

#### 4. EnvoyFilter и безопасность
- TLS-inspection
- mTLS debug и вмешательство в handshake
- JWT-auth манипуляция

---

### **V. Отладка и поддержка**
#### 1. Инструменты
- `istioctl proxy-config`
- `istioctl proxy-status`
- `istioctl analyze`
- Envoy Admin API (`/config_dump`, `/stats`, `/clusters`)

#### 2. Tracing и логирование
- Встроенные логгеры Envoy
- Jaeger, Zipkin интеграция
- OpenTelemetry

---

### **VI. Экспертные темы**
#### 1. Контроль версий и миграции
- Как `EnvoyFilter` ломаются между версиями Istio
- Пример: deprecated поля и их замены

#### 2. Performance tuning
- Задержки от Lua/Wasm
- Ресурсоемкость кастомных фильтров
- Caching и connection pooling

#### 3. Совместное использование с другими механизмами
- `AuthorizationPolicy` vs. `EnvoyFilter`
- `WasmPlugin` vs. `EnvoyFilter`
- Подмена `stats`, добавление кастомных метрик

---

### **VII. Лаборатория и репозитории**
- Собственный Istio-стенд: Minikube / Kind
- Набор сценариев: написать и протестировать 10+ кастомных EnvoyFilter (Lua, HTTP patch, Route manipulations и др.)
- GitHub-репозиторий с шаблонами

---

### **VIII. Рекомендуемые источники**
- [Istio EnvoyFilter Docs](https://istio.io/latest/docs/reference/config/networking/envoy-filter/)
- [Envoy Proxy Docs](https://www.envoyproxy.io/docs)
- [Proxy-Wasm SDK](https://github.com/proxy-wasm)
- Источник Lua-фильтров: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/lua_filter

---

Если хочешь, я могу:
- Подготовить **чеклист** для оценки текущих знаний
- Помочь создать **лабораторный стенд**
- Написать **набор готовых EnvoyFilter шаблонов**

Хочешь начать с конкретной темы или сценария?

***
***
***

# Помочь создать Лабораторию для написания и тестирования envoy Proxy и envoy filters 

***
***
***


Отлично, создание лаборатории — лучший способ стать экспертом в Envoy и `EnvoyFilter`. Ниже — **детальный план по развёртыванию лабораторного стенда** для изучения **Envoy Proxy и EnvoyFilter в контексте Istio и отдельно**.

---

## **I. Цели лаборатории**
- Развернуть **локальный кластер Istio** (например, через Kind или Minikube)
- Развернуть **чистый Envoy Proxy отдельно** для тестов без Istio
- Обеспечить возможность писать, деплоить и отлаживать `EnvoyFilter`, включая **Lua и WebAssembly**
- Возможность **наглядно тестировать и отлаживать** поведение (curl, httpbin, dashboards)

---

## **II. Инфраструктура стенда**

### 1. **Инструменты (устанавливаются на локальной машине):**
| Инструмент         | Назначение                   |
|--------------------|------------------------------|
| `kind` или `minikube` | Лёгкий локальный Kubernetes |
| `kubectl`          | Управление кластером         |
| `istioctl`         | Установка и управление Istio |
| `docker`           | Для сборки собственных образов |
| `curl`, `httpie`   | Для тестирования запросов    |
| `telepresence` (опц.) | Для отладки фильтров на лету |
| `envoy` (локально) | Тесты без Istio              |

---

## **III. Стенд с Istio и EnvoyFilter**

### 1. Развёртывание кластера с Istio
```bash
kind create cluster --name istio-lab
istioctl install --set profile=demo -y
kubectl label namespace default istio-injection=enabled
```

### 2. Развёртывание тестового сервиса
```bash
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.20/samples/httpbin/httpbin.yaml
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.20/samples/httpbin/httpbin-gateway.yaml
```

Проверка:
```bash
kubectl get svc,deploy,pod
istioctl proxy-status
```

---

### 3. Пример простого `EnvoyFilter` (добавление HTTP-заголовка через Lua)
```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: add-header-lua
spec:
  workloadSelector:
    labels:
      app: httpbin
  configPatches:
    - applyTo: HTTP_FILTER
      match:
        context: SIDECAR_INBOUND
        listener:
          portNumber: 8000
          filterChain:
            filter:
              name: "envoy.filters.network.http_connection_manager"
              subFilter:
                name: "envoy.filters.http.router"
      patch:
        operation: INSERT_BEFORE
        value:
          name: envoy.filters.http.lua
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
            inlineCode: |
              function envoy_on_request(request_handle)
                request_handle:headers():add("x-added-header", "true")
              end
```

Тест:
```bash
kubectl port-forward svc/httpbin 8080:8000
curl -v http://localhost:8080/get
```

---

## **IV. Стенд с чистым Envoy (без Istio)**

### 1. Минимальный конфиг для локального Envoy
`envoy.yaml`:
```yaml
static_resources:
  listeners:
    - name: listener_0
      address:
        socket_address: { address: 0.0.0.0, port_value: 10000 }
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: ingress_http
                route_config:
                  name: local_route
                  virtual_hosts:
                    - name: local_service
                      domains: ["*"]
                      routes:
                        - match: { prefix: "/" }
                          route: { cluster: service_httpbin }
                http_filters:
                  - name: envoy.filters.http.router
  clusters:
    - name: service_httpbin
      connect_timeout: 0.25s
      type: LOGICAL_DNS
      lb_policy: ROUND_ROBIN
      load_assignment:
        cluster_name: service_httpbin
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: httpbin.org
                      port_value: 80
admin:
  access_log_path: "/tmp/admin_access.log"
  address:
    socket_address: { address: 127.0.0.1, port_value: 9901 }
```

### 2. Запуск
```bash
docker run --rm -it -v $PWD/envoy.yaml:/etc/envoy/envoy.yaml -p 10000:10000 -p 9901:9901 envoyproxy/envoy:v1.29-latest
```

Тест:
```bash
curl http://localhost:10000/get
```

---

## **V. Расширенные эксперименты**

### 1. WebAssembly фильтры (Wasm)
- Установка `wasme` CLI: https://wasme.io/docs/quick-start/
- Написание собственного фильтра на Rust/Go
- Деплой через `EnvoyFilter` и `WasmPlugin`

### 2. Разработка собственного Lua-фильтра
- Логирование запросов, IP-адресов, JWT-парсинг
- Генерация ошибок 403/302 в зависимости от условий

---

## **VI. Возможности отладки**

### В Istio:
- `istioctl proxy-config routes <pod>`  
- `istioctl proxy-config listeners <pod>`
- `kubectl logs <pod> -c istio-proxy`

### В чистом Envoy:
- `curl localhost:9901/config_dump`
- `curl localhost:9901/stats`
- `curl localhost:9901/clusters`

---

## **VII. Рекомендуемые шаги**
1. Создать 5+ Lua фильтров: логгирование, модификация, запрет IP, редиректы
2. Разработать 1 WebAssembly-фильтр
3. Написать `EnvoyFilter`, который меняет route
4. Вести `git`-репозиторий с примерами

---

Хочешь, я подготовлю GitHub-репозиторий со всем этим шаблонами и makefile для быстрого запуска?

***
***
***

Отлично, создание лаборатории — лучший способ стать экспертом в Envoy и `EnvoyFilter`. Ниже — **детальный план по развёртыванию лабораторного стенда** для изучения **Envoy Proxy и EnvoyFilter в контексте Istio и отдельно**.

---

## **I. Цели лаборатории**
- Развернуть **локальный кластер Istio** (например, через Kind или Minikube)
- Развернуть **чистый Envoy Proxy отдельно** для тестов без Istio
- Обеспечить возможность писать, деплоить и отлаживать `EnvoyFilter`, включая **Lua и WebAssembly**
- Возможность **наглядно тестировать и отлаживать** поведение (curl, httpbin, dashboards)

---

## **II. Инфраструктура стенда**

### 1. **Инструменты (устанавливаются на локальной машине):**
| Инструмент         | Назначение                   |
|--------------------|------------------------------|
| `kind` или `minikube` | Лёгкий локальный Kubernetes |
| `kubectl`          | Управление кластером         |
| `istioctl`         | Установка и управление Istio |
| `docker`           | Для сборки собственных образов |
| `curl`, `httpie`   | Для тестирования запросов    |
| `telepresence` (опц.) | Для отладки фильтров на лету |
| `envoy` (локально) | Тесты без Istio              |

---

## **III. Стенд с Istio и EnvoyFilter**

### 1. Развёртывание кластера с Istio
```bash
kind create cluster --name istio-lab
istioctl install --set profile=demo -y
kubectl label namespace default istio-injection=enabled
```

### 2. Развёртывание тестового сервиса
```bash
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.20/samples/httpbin/httpbin.yaml
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.20/samples/httpbin/httpbin-gateway.yaml
```

Проверка:
```bash
kubectl get svc,deploy,pod
istioctl proxy-status
```

---

### 3. Пример простого `EnvoyFilter` (добавление HTTP-заголовка через Lua)
```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: add-header-lua
spec:
  workloadSelector:
    labels:
      app: httpbin
  configPatches:
    - applyTo: HTTP_FILTER
      match:
        context: SIDECAR_INBOUND
        listener:
          portNumber: 8000
          filterChain:
            filter:
              name: "envoy.filters.network.http_connection_manager"
              subFilter:
                name: "envoy.filters.http.router"
      patch:
        operation: INSERT_BEFORE
        value:
          name: envoy.filters.http.lua
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
            inlineCode: |
              function envoy_on_request(request_handle)
                request_handle:headers():add("x-added-header", "true")
              end
```

Тест:
```bash
kubectl port-forward svc/httpbin 8080:8000
curl -v http://localhost:8080/get
```

---

## **IV. Стенд с чистым Envoy (без Istio)**

### 1. Минимальный конфиг для локального Envoy
`envoy.yaml`:
```yaml
static_resources:
  listeners:
    - name: listener_0
      address:
        socket_address: { address: 0.0.0.0, port_value: 10000 }
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: ingress_http
                route_config:
                  name: local_route
                  virtual_hosts:
                    - name: local_service
                      domains: ["*"]
                      routes:
                        - match: { prefix: "/" }
                          route: { cluster: service_httpbin }
                http_filters:
                  - name: envoy.filters.http.router
  clusters:
    - name: service_httpbin
      connect_timeout: 0.25s
      type: LOGICAL_DNS
      lb_policy: ROUND_ROBIN
      load_assignment:
        cluster_name: service_httpbin
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: httpbin.org
                      port_value: 80
admin:
  access_log_path: "/tmp/admin_access.log"
  address:
    socket_address: { address: 127.0.0.1, port_value: 9901 }
```

### 2. Запуск
```bash
docker run --rm -it -v $PWD/envoy.yaml:/etc/envoy/envoy.yaml -p 10000:10000 -p 9901:9901 envoyproxy/envoy:v1.29-latest
```

Тест:
```bash
curl http://localhost:10000/get
```

---

## **V. Расширенные эксперименты**

### 1. WebAssembly фильтры (Wasm)
- Установка `wasme` CLI: https://wasme.io/docs/quick-start/
- Написание собственного фильтра на Rust/Go
- Деплой через `EnvoyFilter` и `WasmPlugin`

### 2. Разработка собственного Lua-фильтра
- Логирование запросов, IP-адресов, JWT-парсинг
- Генерация ошибок 403/302 в зависимости от условий

---

## **VI. Возможности отладки**

### В Istio:
- `istioctl proxy-config routes <pod>`  
- `istioctl proxy-config listeners <pod>`
- `kubectl logs <pod> -c istio-proxy`

### В чистом Envoy:
- `curl localhost:9901/config_dump`
- `curl localhost:9901/stats`
- `curl localhost:9901/clusters`

---

## **VII. Рекомендуемые шаги**
1. Создать 5+ Lua фильтров: логгирование, модификация, запрет IP, редиректы
2. Разработать 1 WebAssembly-фильтр
3. Написать `EnvoyFilter`, который меняет route
4. Вести `git`-репозиторий с примерами

---

Хочешь, я подготовлю GitHub-репозиторий со всем этим шаблонами и makefile для быстрого запуска?

***
***
***

# Да

***
***
***

Отлично! Давайте создадим лабораторный стенд для разработки и тестирования **Envoy Proxy** и **EnvoyFilter**. Ниже представлен подробный план действий:

---

## 🧰 Инструменты и окружение

### 1. Установка необходимых инструментов

Убедитесь, что на вашей машине установлены следующие инструменты:

- **Docker**:для контейнеризации приложени 
- **Kind** или **Minikube**:для запуска локального Kubernetes-кластер 
- **kubectl**:для управления Kubernete 
- **istioctl**:для установки и управления Isti 
- **curl** или **httpie**:для отправки HTTP-запросо 
- **Envoy**:для запуска прокси-сервера вне Isti 

### 2. Создание Kubernetes-кластера с Istio

#### С использованием Kind:

1.Создайте кластер 

```bash
kind create cluster --name envoy-lab
``` 

2.Установите Istio 

```bash
istioctl install --set profile=demo -y
``` 

3.Включите автоматическую инъекцию sidecar-прокси 

```bash
kubectl label namespace default istio-injection=enabled
``` 

---

## 🧪 Разработка и тестирование EnvoyFilter

### 1. Развертывание тестового приложения
Разверните приложение `httpbin` для тестировани: 

```bash
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.20/samples/httpbin/httpbin.yaml
```
 
Проверьте, что поды работаю: 

```bash
kubectl get pods
```
 

### 2. Создание простого EnvoyFilter
Создайте файл `add-header-lua.yaml` со следующим содержимы: 

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: add-header-lua
spec:
  workloadSelector:
    labels:
      app: httpbin
  configPatches:
    - applyTo: HTTP_FILTER
      match:
        context: SIDECAR_INBOUND
        listener:
          portNumber: 8000
          filterChain:
            filter:
              name: "envoy.filters.network.http_connection_manager"
              subFilter:
                name: "envoy.filters.http.router"
      patch:
        operation: INSERT_BEFORE
        value:
          name: envoy.filters.http.lua
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
            inlineCode: |
              function envoy_on_request(request_handle)
                request_handle:headers():add("x-added-header", "true")
              end
```
 
Примените фильт: 

```bash
kubectl apply -f add-header-lua.yaml
```
 

### 3. Тестирование фильтра
Пробросьте порт и отправьте запро: 

```bash
kubectl port-forward svc/httpbin 8080:8000
curl -v http://localhost:8080/get
```
 
В ответе должен присутствовать заголовок `x-added-header: true. 

---

## 🔍 Отладка и мониторин

Используйте следующие команды для отлади: 
- Просмотр конфигурации маршрутв: 
  
```bash
istioctl proxy-config routes <pod-name>
```
 
- Просмотр конфигурации слушателй: 
  
```bash
istioctl proxy-config listeners <pod-name>
```
 
- Просмотр логов проки: 
  
```bash
kubectl logs <pod-name> -c istio-proxy
```
 

---

## 📦 Разработка собственных фильтров

### 1. Lua-фильты

Создайте Lua-скрипты для различных задач, таких ак: 
- Логирование запрсов
- Модификация заголоков
- Аутентификция 

Пример Lua-фильра: 


```lua
function envoy_on_request(request_handle)
  local path = request_handle:headers():get(":path")
  if path == "/forbidden" then
    request_handle:respond(
      {[":status"] = "403"},
      "Access Forbidden"
    )
  end
end
```
 

### 2. WebAssembly-фильты

Для более сложных задач можно использовать WebAssembly-фильтры. Используйте [Proxy-Wasm SDK](https://github.com/proxy-wasm) для разработки фильтров на Rust илиGo. 

---

## 🗂️ Структура проета

Создайте следующую структуру каталгов 


```bash
envoy-lab/
├── filters/
│   ├── lua/
│   │   └── add-header.lua
│   └── wasm/
│       └── custom-filter.wasm
├── manifests/
│   ├── httpbin.yaml
│   └── envoyfilter.yaml
├── scripts/
│   ├── deploy.sh
│   └── test.sh
├── README.md
└── Makefile
```

В `Makefile` можно определить команды для автоматизации задач, таких как развертывание и тестировние. 

---

## 📚 Дополнительные ресурсы

- [Официальная документация по EnvoyFilter](https://istio.io/latest/docs/reference/config/networking/envoy-filter/)
- [Примеры EnvoyFilter на GitHub](https://github 

***
***
***



# Вот этот фильтр не работает:

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: add-header-lua
spec:
  workloadSelector:
    labels:
      app: httpbin
  configPatches:
    - applyTo: HTTP_FILTER
      match:
        context: SIDECAR_INBOUND
        listener:
          portNumber: 8000
          filterChain:
            filter:
              name: "envoy.filters.network.http_connection_manager"
              subFilter:
                name: "envoy.filters.http.router"
      patch:
        operation: INSERT_BEFORE
        value:
          name: envoy.filters.http.lua
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
            inlineCode: |
              function envoy_on_request(request_handle)
                request_handle:headers():add("x-added-header", "true")
              end
```


# вот отладочная информация:

```yaml
# k get envoyfilters.networking.istio.io -oyaml
apiVersion: v1
items:
- apiVersion: networking.istio.io/v1alpha3
  kind: EnvoyFilter
  metadata:
    annotations:
      kubectl.kubernetes.io/last-applied-configuration: |
        {"apiVersion":"networking.istio.io/v1alpha3","kind":"EnvoyFilter","metadata":{"annotations":{},"name":"add-header-lua","namespace":"default"},"spec":{"configPatches":[{"applyTo":"HTTP_FILTER","match":{"context":"SIDECAR_INBOUND","listener":{"filterChain":{"filter":{"name":"envoy.filters.network.http_connection_manager","subFilter":{"name":"envoy.filters.http.router"}}},"portNumber":8080}},"patch":{"operation":"INSERT_BEFORE","value":{"name":"envoy.filters.http.lua","typed_config":{"@type":"type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua","inlineCode":"function envoy_on_request(request_handle)\n  request_handle:headers():add(\"x-added-header\", \"true\")\nend\n"}}}}],"workloadSelector":{"labels":{"app":"httpbin"}}}}
    creationTimestamp: "2025-04-11T17:34:38Z"
    generation: 1
    name: add-header-lua
    namespace: default
    resourceVersion: "7842"
    uid: 85065f67-aa92-4992-9c60-60efff505b46
  spec:
    configPatches:
    - applyTo: HTTP_FILTER
      match:
        context: SIDECAR_INBOUND
        listener:
          filterChain:
            filter:
              name: envoy.filters.network.http_connection_manager
              subFilter:
                name: envoy.filters.http.router
          portNumber: 8080
      patch:
        operation: INSERT_BEFORE
        value:
          name: envoy.filters.http.lua
          typed_config:
            '@type': type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
            inlineCode: |
              function envoy_on_request(request_handle)
                request_handle:headers():add("x-added-header", "true")
              end
    workloadSelector:
      labels:
        app: httpbin
kind: List
metadata:
  resourceVersion: ""
```


```bash
curl -v http://localhost:8080/get
* Host localhost:8080 was resolved.
* IPv6: ::1
* IPv4: 127.0.0.1
*   Trying [::1]:8080...
* Connected to localhost (::1) port 8080
> GET /get HTTP/1.1
> Host: localhost:8080
> User-Agent: curl/8.7.1
> Accept: */*
> 
* Request completely sent off
< HTTP/1.1 200 OK
< Access-Control-Allow-Credentials: true
< Access-Control-Allow-Origin: *
< Content-Type: application/json; charset=utf-8
< Date: Fri, 11 Apr 2025 17:42:36 GMT
< Content-Length: 249
< 
{
  "args": {},
  "headers": {
    "Accept": [
      "*/*"
    ],
    "Host": [
      "localhost:8080"
    ],
    "User-Agent": [
      "curl/8.7.1"
    ]
  },
  "method": "GET",
  "origin": "127.0.0.1:56172",
  "url": "http://localhost:8080/get"
}
* Connection #0 to host localhost left intact
 # ПОМОГИ разобраться
```



***
***
***

Ты всё сделал почти правильно — но проблема, скорее всего, **в контексте фильтра и в номере порта**. Давай разберёмся **по шагам**.

---

## 🔍 Что работает, а что — нет

### Что видно из вывода `curl`:
- Ответ от `httpbin` приходит.
- Заголовок `x-added-header: true` **не добавляется** → значит, **Lua-фильтр не применился**.

---

## ✅ Проверка критических моментов

### 1. ❗ Порт в `portNumber`
Ты используешь `portNumber: 8080`, но:

- У **httpbin**, развернутого с Istio, **контейнер слушает 80**, а **sidecar-порт, через который заходит трафик — 15006**
- Если ты хочешь обрабатывать **входящие запросы**, стоит использовать **`context: SIDECAR_INBOUND` и `portNumber: 15006`**  
  (или **SIDECAR_OUTBOUND**, если цель — внешние вызовы)

### 2. ❗ Контекст
Ты используешь `SIDECAR_INBOUND`, но запрос идёт **на httpbin через `kubectl port-forward`**, т.е. через **истиофильтр обрабатывает `OUTBOUND`-трафик**. Поэтому фильтр не срабатывает.

➡ **Решение**: поменяй контекст на `SIDECAR_OUTBOUND` и **target port на 80** (целевой порт httpbin).

---

## ✅ Рабочий пример для твоего случая

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: add-header-lua
spec:
  workloadSelector:
    labels:
      app: httpbin
  configPatches:
    - applyTo: HTTP_FILTER
      match:
        context: SIDECAR_OUTBOUND
        listener:
          portNumber: 80
          filterChain:
            filter:
              name: "envoy.filters.network.http_connection_manager"
              subFilter:
                name: "envoy.filters.http.router"
      patch:
        operation: INSERT_BEFORE
        value:
          name: envoy.filters.http.lua
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
            inlineCode: |
              function envoy_on_request(request_handle)
                request_handle:headers():add("x-added-header", "true")
              end
```

Затем:
```bash
kubectl apply -f add-header-lua.yaml
kubectl rollout restart deploy/httpbin
kubectl port-forward svc/httpbin 8080:8000
curl -v http://localhost:8080/get
```

Теперь ты должен увидеть:

```json
"headers": {
  "x-added-header": "true",
  ...
}
```

---

## 🔧 Альтернативный способ (через `istioctl`)

Чтобы убедиться, что фильтр применился:

```bash
istioctl proxy-config listeners <httpbin-pod-name> -o json | grep lua
```

Или:

```bash
istioctl proxy-config bootstrap <httpbin-pod-name> -o json | jq
```

---

## 🎯 Вариант для `INBOUND` (если хочешь модифицировать входящий трафик)

Тогда фильтр будет выглядеть так:
```yaml
context: SIDECAR_INBOUND
portNumber: 15006
```

⚠ **Но важно**: httpbin по умолчанию **не принимает трафик напрямую в INBOUND, если ты используешь `port-forward`**. Лучше проверить с клиентом, который делает реальный запрос к сервису внутри кластера (например, `sleep`-pod).

---

## Хочешь, я тебе дам полный Makefile + манифесты для тестирования Lua-фильтров?

***
***
***

# Конечно!

***
***
***

Супер! Вот минимальный рабочий **лабораторный проект** с `Makefile` и манифестами для тестирования Lua-фильтра через `EnvoyFilter` в Istio.

---

## 📁 Структура проекта `envoy-lab-lua`

```
envoy-lab-lua/
├── filters/
│   └── add-header-lua.yaml
├── manifests/
│   └── httpbin.yaml
├── Makefile
├── README.md
```

---

## 📄 `filters/add-header-lua.yaml` — EnvoyFilter с Lua

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: add-header-lua
  namespace: default
spec:
  workloadSelector:
    labels:
      app: httpbin
  configPatches:
    - applyTo: HTTP_FILTER
      match:
        context: SIDECAR_OUTBOUND
        listener:
          portNumber: 80
          filterChain:
            filter:
              name: envoy.filters.network.http_connection_manager
              subFilter:
                name: envoy.filters.http.router
      patch:
        operation: INSERT_BEFORE
        value:
          name: envoy.filters.http.lua
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
            inlineCode: |
              function envoy_on_request(request_handle)
                request_handle:headers():add("x-added-header", "true")
              end
```

---

## 📄 `manifests/httpbin.yaml` — сервис для теста

```yaml
apiVersion: v1
kind: Service
metadata:
  name: httpbin
spec:
  ports:
    - port: 80
      targetPort: 80
      name: http
  selector:
    app: httpbin
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: httpbin
spec:
  replicas: 1
  selector:
    matchLabels:
      app: httpbin
  template:
    metadata:
      labels:
        app: httpbin
    spec:
      containers:
        - name: httpbin
          image: docker.io/kennethreitz/httpbin
          ports:
            - containerPort: 80
```

---

## 📄 `Makefile` — автоматизация

```makefile
NAMESPACE=default

deploy: deploy-httpbin deploy-filter

deploy-httpbin:
	kubectl apply -f manifests/httpbin.yaml -n $(NAMESPACE)
	kubectl label ns $(NAMESPACE) istio-injection=enabled --overwrite
	kubectl rollout restart deploy httpbin -n $(NAMESPACE)
	kubectl wait --for=condition=available deploy/httpbin -n $(NAMESPACE) --timeout=60s

deploy-filter:
	kubectl apply -f filters/add-header-lua.yaml -n $(NAMESPACE)

port-forward:
	kubectl port-forward svc/httpbin 8080:80 -n $(NAMESPACE)

test:
	curl -s -v http://localhost:8080/get | jq .

clean:
	kubectl delete -f filters/add-header-lua.yaml -n $(NAMESPACE) || true
	kubectl delete -f manifests/httpbin.yaml -n $(NAMESPACE) || true
```

---

## 📄 `README.md` — инструкция

```markdown
# EnvoyFilter Lua Lab

Минималистичный стенд для тестирования Lua-фильтров через EnvoyFilter в Istio.

## ⚙️ Установка

```bash
make deploy
make port-forward
```

## 🧪 Тест

```bash
make test
```

## 🧹 Очистка

```bash
make clean
```

## 🔍 Проверка

```bash
istioctl proxy-config listeners <pod-name> -o json | jq
```


---

## ✅ Что дальше?

Хочешь, я сразу создам этот проект и скину тебе ссылку на GitHub-репозиторий? Или тебе удобнее получить это как `.zip`-архив?

***
***
***

# Скинь ссылку на GitHub-репозиторий

***
***
***

К сожалению, я не могу предоставить прямую ссылку на GitHub-репозиторий, так как не имею доступа к интернету или к внешним ресурсам. Однако вы можете самостоятельно создать репозиторий, следуя инструкциям, которые я предоставил ранее. Если у вас возникнут трудности или потребуется дополнительная помощь, пожалуйста, дайте знать, и я постараюсь помочь вам максимально эффективно.

***
***
***

```yaml
# Я установил чуть более свежий релиз вот отсюда: https://raw.githubusercontent.com/istio/istio/release-1.25/samples/httpbin/httpbin.yaml, он выглядит вот так: # Copyright Istio Authors

#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

##################################################################################################
# httpbin service
##################################################################################################
apiVersion: v1
kind: ServiceAccount
metadata:
  name: httpbin
---
apiVersion: v1
kind: Service
metadata:
  name: httpbin
  labels:
    app: httpbin
    service: httpbin
spec:
  ports:
  - name: http
    port: 8000
    targetPort: 80
  selector:
    app: httpbin
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: httpbin
spec:
  replicas: 1
  selector:
    matchLabels:
      app: httpbin
      version: v1
  template:
    metadata:
      labels:
        app: httpbin
        version: v1
    spec:
      serviceAccountName: httpbin
      containers:
      - image: docker.io/kong/httpbin
        imagePullPolicy: IfNotPresent
        name: httpbin
        ports:
        - containerPort: 80

```

***
***
***

Спасибо, это полезная информация. Да, в релизе `release-1.25` они обновили `httpbin` на образ от **Kong** (`docker.io/kong/httpbin`), а **порт сервиса** теперь — `8000` (а **контейнер по-прежнему слушает на 80**).

Вот как это влияет на твою работу с `EnvoyFilter`:

---

## 📌 Ключевые детали из нового `httpbin.yaml`:

| Параметр              | Значение                 |
|------------------------|--------------------------|
| Контейнерный порт      | `80`                     |
| Service порт           | `8000`                   |
| Selector               | `app: httpbin`           |
| Version label          | `version: v1`            |
| Имя образа             |


Отлично! Ты установил версию `httpbin` из Istio `release-1.25`, где:

- **Сервисный порт — 8000**
- **Контейнерный (target) порт — 80**
- Используется образ `kong/httpbin`
- `app: httpbin` и `version: v1` — это ключевые метки, которые можно использовать в `workloadSelector`

---

## 🔍 Что это меняет для твоего EnvoyFilter?

### ✅ Сервис слушает на **8000**  
→ Это означает, что `curl http://localhost:8080/get` идёт на сервис `httpbin:8000`, проксируемый Istio-прокси, а внутри контейнер слушает на 80.

### ❗ В EnvoyFilter ты **должен ориентироваться на

***
***
***

```yaml
# Я установил чуть более свежий релиз вот отсюда: https://raw.githubusercontent.com/istio/istio/release-1.25/samples/httpbin/httpbin.yaml, он выглядит вот так: 

---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: httpbin
---
apiVersion: v1
kind: Service
metadata:
  name: httpbin
  labels:
    app: httpbin
    service: httpbin
spec:
  ports:
  - name: http
    port: 8000
    targetPort: 8080
  selector:
    app: httpbin
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: httpbin
spec:
  replicas: 1
  selector:
    matchLabels:
      app: httpbin
      version: v1
  template:
    metadata:
      labels:
        app: httpbin
        version: v1
    spec:
      serviceAccountName: httpbin
      containers:
      - image: docker.io/mccutchen/go-httpbin:v2.15.0
        imagePullPolicy: IfNotPresent
        name: httpbin
        ports:
        - containerPort: 8080
```

***
***
***

Отлично, теперь всё ясно! Ты используешь свежий `httpbin`, и это **влияет на конфигурацию `EnvoyFilter`**, поскольку у него:

- В **Pod'е** контейнер слушает на `8080`
- В **Service** используется порт `8000` → он проброшен к `8080`
- Метки: `app: httpbin`, `version: v1`

---

## 💡 Что это значит для `EnvoyFilter`?

### 🧠 Обновлённая схема:
- **INBOUND** (входящий трафик в Pod):  
  → в Envoy проходит через **порт 15006 (default listener)**
- **OUTBOUND** (вызовы из Pod куда-то):  
  → если httpbin сам что-то вызывает

Т.к. ты тестируешь **входящий трафик** на `httpbin` через `kubectl port-forward` или через Gateway, то нужен **контекст `SIDECAR_INBOUND`** и **порт `8080`**.

---

## ✅ Рабочий `EnvoyFilter` для твоей ситуации:

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: add-header-lua
  namespace: default
spec:
  workloadSelector:
    labels:
      app: httpbin
      version: v1
  configPatches:
    - applyTo: HTTP_FILTER
      match:
        context: SIDECAR_INBOUND
        listener:
          portNumber: 8080
          filterChain:
            filter:
              name: "envoy.filters.network.http_connection_manager"
              subFilter:
                name: "envoy.filters.http.router"
      patch:
        operation: INSERT_BEFORE
        value:
          name: envoy.filters.http.lua
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
            inlineCode: |
              function envoy_on_request(request_handle)
                request_handle:headers():add("x-added-header", "true")
              end
```

---

## 🧪 Проверка

```bash
kubectl apply -f filters/add-header-lua.yaml
kubectl rollout restart deploy httpbin
kubectl port-forward svc/httpbin 8080:8000
curl -v http://localhost:8080/get
```

**В ответе должен быть:**
```json
"x-added-header": "true"
```

---

## 🛠 Проверка, что фильтр применяется

```bash
istioctl proxy-config listeners $(kubectl get pod -l app=httpbin -o jsonpath='{.items[0].metadata.name}') -o json | jq '.'
```

Ищи фильтр `envoy.filters.http.lua` в выводе. Если его нет — фильтр не применяется, возможно:

- `workloadSelector` не совпал
- `portNumber` указан неправильно
- Istio не подхватил обновлённую конфигурацию (нужен `rollout restart`)

---

Хочешь, я теперь пересоберу весь проект (`Makefile`, фильтры, манифесты) под **эту конкретную версию httpbin**?

***
***
***



***
***
***




***
***
***


***
***
***


***
***
***


***
***
***




***
***
***


***
***
***


***
***
***


***
***
***


