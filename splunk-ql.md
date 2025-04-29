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



***
***
***

 Below is a focused troubleshooting playbook that explains **why строковый поиск по <APP_NAME>-<CLUSTER_DNS> ничего не находит** и показывает, как быстро вытянуть нужный виртуальный хост из логов Ingress-Nginx в Splunk.

---

## Вкратце (ключевая причина)

Контейнерные логи, которые Splunk Connect for Kubernetes (SC4K) доставляет во внешний Splunk, приходят как **обёртка-JSON** (поле `log`), внутри которой сидит ещё один JSON-access-log Nginx. Строковый поиск (`"<APP_NAME>-<CLUSTER_DNS>"`) проверяет только видимую строку в первом слое; поэтому, пока вы не распакуете вложенный JSON (командой `spath` или через `KV_MODE=json / INDEXED_EXTRACTIONS=JSON`), Splunk «не видит» содержание поля `vhost`. ([splunk/splunk-connect-for-kubernetes: Helm charts associated with ...](https://github.com/splunk/splunk-connect-for-kubernetes?utm_source=chatgpt.com), [How to use spath with string formatted events? - Splunk Community](https://community.splunk.com/t5/Splunk-Search/How-to-use-spath-with-string-formatted-events/m-p/670568?utm_source=chatgpt.com), [spath - Splunk Documentation](https://docs.splunk.com/Documentation/Splunk/9.4.1/SearchReference/Spath?utm_source=chatgpt.com))

---

## 1 Проверьте, где именно лежит `vhost`

1. Выполните базовый поиск и откройте **сырой (_raw_)** ивент:

   ```spl
   index=platform*  sourcetype="kube:container:controller"
   | head 1
   ```

   Скорее всего вы увидите что-то вроде:

   ```json
   {
     "time":"2025-04-29T10:22:13Z",
     "log":"{\"correlation\":\"…\",\"vhost\":\"my-app.dev.example.com\",\"uri\":\"/\",\"status\":200,…}"
   }
   ```

   Обратите внимание: поле `vhost` находится **внутри строки `log`** – то есть на втором уровне JSON. ([How to parse string JSON along with actual JSON?](https://community.splunk.com/t5/Splunk-Search/How-to-parse-string-JSON-along-with-actual-JSON/m-p/594713?search-action-id=182932756620&search-result-uid=594713&utm_source=chatgpt.com), [How to extract fields from JSON which is stored in another field?](https://community.splunk.com/t5/Splunk-Search/How-to-extract-fields-from-JSON-which-is-stored-in-another-field/m-p/227479?utm_source=chatgpt.com))

---

## 2 Одноразовый «ad-hoc» поиск по конкретному vhost

```spl
index=platform* sourcetype="kube:container:controller"
| spath input=log               ← распаковываем вложенный JSON
| search vhost="my-app.dev.example.com"
| stats count by status uri
```

* `spath` умеет доставать любые поля из JSON внутри другого поля; параметр `input=` указывает, что нужно разбирать именно `log`. ([spath - Splunk Documentation](https://docs.splunk.com/Documentation/Splunk/9.4.1/SearchReference/Spath?utm_source=chatgpt.com), [How to use spath with string formatted events? - Splunk Community](https://community.splunk.com/t5/Splunk-Search/How-to-use-spath-with-string-formatted-events/m-p/670568?utm_source=chatgpt.com))  
* После `spath` поле `vhost` становится полноценным и фильтр `search vhost=…` отрабатывает.  

---

## 3 Извлечение регуляркой, если `spath` не подходит

Если по каким-то причинам JSON ломанный или слишком длинный (>5 KБ, спath по-умолчанию обрезает) ([spath - Splunk Documentation](https://docs.splunk.com/Documentation/Splunk/9.4.1/SearchReference/Spath?utm_source=chatgpt.com)):

```spl
index=platform* sourcetype="kube:container:controller"
| rex field=log "\"vhost\":\"(?<vhost>[^\"]+)\""
| search vhost="my-app.dev.example.com"
```

---

## 4 «Перманентное» решение через props.conf

Чтобы больше не писать `spath/rex`, включите автоматическое парсирование:

```conf
# $SPLUNK_HOME/etc/apps/SC4K/local/props.conf
[kube:container:controller]
KV_MODE = json          # включает JSON-KV-Mode на этапе поиска ([props.conf - Splunk Documentation](https://docs.splunk.com/Documentation/Splunk/latest/admin/propsconf?utm_source=chatgpt.com), [Extract fields from files with structured data - Splunk Documentation](https://docs.splunk.com/Documentation/Splunk/9.4.0/Data/Extractfieldsfromfileswithstructureddata?utm_source=chatgpt.com))
AUTO_KV_JSON = true     # явно говорим распознавать все ключи
```

*Если у вас есть доступ к индекс-тайму*, можно добиться ещё быстрее:

```conf
[kube:container:controller]
INDEXED_EXTRACTIONS = JSON   # ключи будут индекс-тайм-поля (быстрее поиск) ([Extract fields from files with structured data - Splunk Documentation](https://docs.splunk.com/Documentation/Splunk/9.4.0/Data/Extractfieldsfromfileswithstructureddata?utm_source=chatgpt.com))
```

После рестарта Splunk достаточно написать просто:

```spl
index=platform* sourcetype="kube:container:controller" vhost="my-app.dev.example.com"
```

---

## 5 Типичные причины, почему поиск не отдавал событий

| Причина | Как проверить / исправить |
|---------|---------------------------|
| **`KV_MODE` выключен** | Откройте _raw_: если `vhost` внутри `"log":"{...}"`, но в панели «Interesting Fields» нет поля `vhost`, значит JSON не извлечён. Включите `KV_MODE=json` или используйте `spath`. ([props.conf - Splunk Documentation](https://docs.splunk.com/Documentation/Splunk/latest/admin/propsconf?utm_source=chatgpt.com)) |
| **Обрезка события** (`extraction_cutoff=5000`) | Длинные access-логи могут не парситься `spath` целиком. Увеличьте лимит в `limits.conf` или примените `rex`, который не зависит от этого. ([spath - Splunk Documentation](https://docs.splunk.com/Documentation/Splunk/9.4.1/SearchReference/Spath?utm_source=chatgpt.com)) |
| **Иной index / sourcetype** | Иногда SC4K пишет в индекс `kube-logs`, а не `platform*`; проверьте аннотацию `splunk.com/index` и Helm-values. ([splunk/splunk-connect-for-kubernetes: Helm charts associated with ...](https://github.com/splunk/splunk-connect-for-kubernetes?utm_source=chatgpt.com), [splunk-connect-for-kubernetes/helm-chart/splunk-connect ... - GitHub](https://github.com/splunk/splunk-connect-for-kubernetes/blob/develop/helm-chart/splunk-connect-for-kubernetes/values.yaml?utm_source=chatgpt.com)) |
| **Часть hostname** | Если домен содержит точки, не забывайте, что Splunk ищет подстрокой: `dev.example.com` найдёт и `my-app.dev.example.com`. |
| **Кавычки в запросе** | Поиск `"my-app.dev.example.com"` внутри кавычек ищет *точную* строку; если в raw она без кавычек, то нужно убрать их. |

---

## 6 Полезные паттерны SPL на каждый день

### График 5xx ошибок по vhost

```spl
index=platform* sourcetype="kube:container:controller"
| spath input=log
| search vhost="my-app.dev.example.com" status>=500
| timechart span=1m count
```

### Топ URI по конкретному хосту

```spl
index=platform* sourcetype="kube:container:controller"
| spath input=log
| search vhost="my-app.dev.example.com" status!=404
| top limit=20 uri
```

---

## 7 Что делать, если `vhost` всё же отсутствует в логах

1. Убедитесь, что контроллер стартует с `--enable-json-logs=true`; без этой опции он пишет plain-text, где `vhost` может не сериализоваться. ([splunk/splunk-connect-for-kubernetes: Helm charts associated with ...](https://github.com/splunk/splunk-connect-for-kubernetes?utm_source=chatgpt.com))  
2. Проверьте ConfigMap ещё раз: `$host` должен быть внутри **того же** `log-format-upstream`, с которого вы читаете (`log-format-upstream` vs `log-format-escape-json`). ([configMap.yaml - GitHub](https://github.com/splunk/splunk-connect-for-kubernetes/blob/develop/manifests/splunk-kubernetes-logging/configMap.yaml?utm_source=chatgpt.com), [Log format type "cri" not working as expected · Issue #357 - GitHub](https://github.com/splunk/splunk-connect-for-kubernetes/issues/357?utm_source=chatgpt.com))  
3. После изменения ConfigMap сделайте `kubectl rollout restart deployment ingress-nginx-controller` — старые pod’ы не подтягивают новую конфигурацию сами.  

---

### Итог

* Поиск не работал, потому что hostname находится на *внутреннем* JSON-уровне.  
* Используйте `spath input=log` **или** настройте `KV_MODE=json` / `INDEXED_EXTRACTIONS=JSON`, чтобы `vhost` стал обычным полем.  
* Тогда запрос вида `index=… vhost="my-app.dev.example.com"` будет мгновенным и надёжным.

После внесения этих настроек вы сможете строить алерты и дашборды по доменам Ingress столь же легко, как по любым другим полям.
