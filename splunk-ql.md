**Коротко:**  
Чтобы в Splunk быстро увидеть HTTP-трафик, который прошёл через Nginx Ingress для конкретного Virtual Host, сначала сузьте поиск по контейнеру ingress-nginx-controller (или его sourcetype), а затем отфильтруйте поле `vhost` / `http_host`. Если такого поля нет, извлеките его регулярным выражением (`rex`) или добавьте в `log_format` контроллера `$host`. Ниже — пошаговый чек-лист с готовыми SPL-примерами, как это сделать в любом окружении K8s + Splunk.

---

## 1. Где именно лежат логи Ingress-Nginx  

| Что | Как проверить в Splunk |
|-----|------------------------|
| **Index** | По умолчанию Splunk Connect for Kubernetes пишет в `main`, но через аннотацию `splunk.com/index=<имя>` можно перенаправить в собственный индекс — проверьте это аннотацией на namespace или pod’е. ([Collect logs and events with the Collector for Kubernetes](https://docs.splunk.com/observability/gdi/opentelemetry/collector-kubernetes/kubernetes-config-logs.html?utm_source=chatgpt.com)) |
| **sourcetype** | При доставке контейнерных логов через SC4K он выглядит как `kube:container:<container_name>` или определённый вручную через `splunk.com/sourcetype`. ([splunk/splunk-connect-for-kubernetes: Helm charts associated with ...](https://github.com/splunk/splunk-connect-for-kubernetes?utm_source=chatgpt.com)) |
| **Контейнер** | В большинстве Helm-чартов контроллер называется `ingress-nginx-controller`; namespace обычно `ingress-nginx`. |

### Быстрый тест

```spl
index=<ваш_индекс>  container_name="ingress-nginx-controller" 
| head 5
```

Если видите обычные access-строки Nginx — значит вы попали в нужный поток.

---

## 2. Убедитесь, что в логе есть виртуальный хост

* **Стандартный log_format Ingress-Nginx** (`upstreaminfo`) не содержит `$host` и выглядит так: `'$remote_addr - $remote_user [$time_local] "$request" … $req_id'` ([Log format - Ingress-Nginx Controller - Kubernetes](https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/log-format/?utm_source=chatgpt.com)).  
* Добавить нужное поле можно через ConfigMap контроллера:  

```yaml
data:
  log-format-upstream: |
    '$http_host $remote_addr - $remote_user [$time_local] "$request" ... $req_id'
```
Это делается тем же способом, что и любая другая настройка Nginx-Ingress через ConfigMap. ([ConfigMap - Ingress-Nginx Controller - Kubernetes](https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/configmap/?utm_source=chatgpt.com))  

> **Проверьте:** после деплоя в raw-строке лога первым токеном появится домен — его легко выделить как `vhost`.

---

## 3. Поиск, если поле уже парсится (лучший вариант)

### 3.1 С аддоном *Splunk Add-on for NGINX*

Если вы используете официальный add-on, sourcetype будет один из `nginx:*:access`, и поле `http_host`/`server_name` уже размечено. ([Source types for the Splunk Add-on for NGINX - Splunk Documentation](https://docs.splunk.com/Documentation/AddOns/released/NGINX/Sourcetypes))

```spl
index=<k8s_index> sourcetype=nginx:plus:access http_host="my-app.example.com"
| stats count by status uri_path
```

### 3.2 Контейнерные логи без add-on, но с JSON-форматом

Многие операторы включают `--enable-json-logs`; тогда поле `vhost` уже есть:

```spl
index=k8s container_name="ingress-nginx-controller" vhost="my-app.example.com"
| timechart span=1m count
```

---

## 4. Поиск, если поля нет (on-the-fly extraction)

### 4.1 Лёгкий «разовый» поиск

```spl
index=k8s container_name="ingress-nginx-controller"
| rex field=_raw "^(?<vhost>[^ ]+)\s"
| search vhost="my-app.example.com"
| stats count by status
```
*Регэкс берёт первый токен до пробела как virtual host.*  

### 4.2 Постоянная пропса (для админов Splunk)

В `props.conf`:

```
[kube:container:ingress-nginx-controller]
EXTRACT-vhost = ^(?<vhost>[^ ]+)\s
```
Теперь поле появится во всех будущих событиях без REX.

---

## 5. Практические советы DevOps-команде

| Задача | Приём |
|--------|-------|
| **Ускорить поиск** | Создайте ускоряемое summary-index или `tsidx`-акселератор по полям `vhost`, `status`, `namespace`. |
| **Повторяемость запроса** | Оформите SPL как макрос, например ``macro_ingress_by_host(host)``. |
| **Отладка 404/502** | Ловите запросы с нужным Host-header (`curl -H "Host: ..."`) и сразу ищите по vhost. ([Accessing ingress-nginx host with host header gives 404 error](https://stackoverflow.com/questions/78380062/accessing-ingress-nginx-host-with-host-header-gives-404-error?utm_source=chatgpt.com)) |
| **Логи корреляции/трейс-ID** | Добавьте в `log_format` свои заголовки (`$http_x_correlation_id`) — пример есть в issue #6483. ([Add custom request headers to log_format · Issue #6483 - GitHub](https://github.com/kubernetes/ingress-nginx/issues/6483?utm_source=chatgpt.com)) |
| **Регэкспы** | Разработайте их в Splunk Field Extractor — см. пример на community. ([Solved: Nginx log parsing - Splunk Community](https://community.splunk.com/t5/Splunk-Search/Nginx-log-parsing/m-p/18620?utm_source=chatgpt.com)) |

---

## 6. Почему так важно фильтровать именно по vhost

Kubernetes Ingress роутит трафик по HTTP Host-заголовку, поэтому одинаковый путь `/` может обслуживать разные back-end’ы на основе домена. ([Ingress - Kubernetes](https://kubernetes.io/docs/concepts/services-networking/ingress/?utm_source=chatgpt.com)) Фильтр по `source` или `pod_name` даст всю мешанину, а `vhost` гарантирует, что вы видите ровно тот виртуальный хост, о котором идёт речь.

---

## 7. Чек-лист «готово к эксплуатации»

1. **Убедитесь, что в логе есть `$host`** (или JSON-ключ `vhost`).  
2. **Проверьте index/sourcetype** (`kube:container`, `nginx:*:access`, `main`, …).  
3. **Создайте REX или props.conf**, если поле не размечено.  
4. **Сохраните SPL как макрос или дэшборд**.  
5. **Настройте alert** на аномальное `status>=500` для конкретного `vhost`.  

С этими шагами поиск нужных записей будет занимать секунды, а не минуты.

---

### Источники  
 ([How to setup Splunk Connect on to capture logs from Kubernetes](https://community.splunk.com/t5/Installation/How-to-setup-Splunk-Connect-on-to-capture-logs-from-Kubernetes/m-p/506590?utm_source=chatgpt.com), [Collect logs and events with the Collector for Kubernetes](https://docs.splunk.com/observability/gdi/opentelemetry/collector-kubernetes/kubernetes-config-logs.html?utm_source=chatgpt.com), [splunk/splunk-connect-for-kubernetes: Helm charts associated with ...](https://github.com/splunk/splunk-connect-for-kubernetes?utm_source=chatgpt.com), [Source types for the Splunk Add-on for NGINX - Splunk Documentation](https://docs.splunk.com/Documentation/AddOns/released/NGINX/Sourcetypes), [Log format - Ingress-Nginx Controller - Kubernetes](https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/log-format/?utm_source=chatgpt.com), [ConfigMap - Ingress-Nginx Controller - Kubernetes](https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/configmap/?utm_source=chatgpt.com), [Ingress - Kubernetes](https://kubernetes.io/docs/concepts/services-networking/ingress/?utm_source=chatgpt.com), [Solved: Nginx log parsing - Splunk Community](https://community.splunk.com/t5/Splunk-Search/Nginx-log-parsing/m-p/18620?utm_source=chatgpt.com), [Add custom request headers to log_format · Issue #6483 - GitHub](https://github.com/kubernetes/ingress-nginx/issues/6483?utm_source=chatgpt.com), [Accessing ingress-nginx host with host header gives 404 error](https://stackoverflow.com/questions/78380062/accessing-ingress-nginx-host-with-host-header-gives-404-error?utm_source=chatgpt.com))
