

Ниже — полностью переписанный EnvoyFilter с Lua-скриптом и аннотацией, который:

* корректно берёт объект SSL через `handle:connection():ssl()`;   
* предпочитает SAN (`dnsSansPeerCertificate()[1]`) и только затем `CN`;  
* удаляет входящий `x-client-cn`, чтобы исключить спуфинг;  
* вставляется прямо **перед** `envoy.filters.http.router`, закреплён «якорём» и имеет `priority`, чтобы гарантировать применение при апгрейдах;  
* добавляет минимальное логирование на уровне `WARN`;  
* оставляет чистый fallback, если клиент пришёл без сертификата либо без SAN/CN.

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: add-client-cn-gateway
spec:
  # Приоритет обязателен для относительных операций
  # (иначе при апгрейде фильтр может «потеряться»)
  priority: 10            # 0 – наивысший, чем больше – тем ниже
  workloadSelector:
    labels:
      istio: ingressgateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
      listener:
        filterChain:
          sni: stack17.app.crds.asm-uk-cdc-01.uat.fichc.intranet.db.com
          # «Якорь» — фильтр Router; вставляемся прямо перед ним
          filter:
            name: envoy.filters.http.router
    patch:
      operation: INSERT_BEFORE
      value:
        name: envoy.filters.http.lua
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
          inlineCode: |
            -- add-client-cn.lua
            function envoy_on_request(handle)
              -- Сброс возможного спуфинга
              handle:headers():remove("x-client-cn")

              local ssl = handle:connection():ssl()
              local client_cn = "no-cert"
              if ssl and ssl:peerCertificatePresented() then
                -- Пытаемся взять SAN DNS, затем CN
                local sans = ssl:dnsSansPeerCertificate()
                if sans and #sans > 0 then
                  client_cn = sans[1]
                else
                  local subj = ssl:parsedSubjectPeerCertificate()
                  if subj then
                    client_cn = subj:commonName() or "missing-cn"
                  end
                end
              end

              handle:headers():replace("x-client-cn", client_cn)
              if client_cn == "no-cert" then
                handle:logWarn("Client came without certificate")
              end
            end
```

---

## Почему именно так

### Lua-API и работа с сертификатом

* `handle:connection():ssl()` — единственный поддерживаемый способ получить объект SSL в Lua; глобальной переменной `ssl` нет. citeturn1view0  
* Метод `peerCertificatePresented()` позволяет быстро проверить, есть ли сертификат. citeturn1view1  
* `dnsSansPeerCertificate()` и `parsedSubjectPeerCertificate():commonName()` дают надёжные поля SAN и CN соответственно. citeturn1view1  
* Заголовки безопаснее писать через `headers():replace`, предварительно вызвав `remove`, чтобы исключить подмену снаружи. citeturn0search11  
* CN исторически устарел: RFC 2818 рекомендует проверять SAN, CN оставлен лишь для обратной совместимости. citeturn0search2  

### Корректная вставка фильтра

* Для относительных операций (`INSERT_BEFORE/AFTER`) Istio требует указать «якорь» и/или `priority`; иначе при изменении набора фильтров или версии прокси порядок станет недетерминированным. citeturn6view0turn10search2  
* Якорем выбран `envoy.filters.http.router`, поскольку он гарантированно есть во всех конфигурациях Gateway и находится в конце цепочки.  
* Значение `priority: 10` устраняет предупреждение `IST0151/IST0155` анализатора и сохраняет порядок во время rolling-upgrade’ов. citeturn10search3  
* Запуск `istioctl analyze` до `kubectl apply`-коммита ловит опечатки в SNI, якоре или относительной операции ещё на CI. citeturn5view0  

### Безопасность мTLS

* Фильтр имеет смысл только при **MUTUAL TLS** на Gateway: настроены `mode: MUTUAL` и в секрете загружен `ca.crt`, иначе прокси примет любой self-signed CN. citeturn0search6  

### Наблюдаемость

* `handle:logWarn` фиксирует редкие, но критичные случаи («клиент без сертификата») в логи Envoy; к ним легко привязать алерт. Lua-API предоставляет пять уровней логов. citeturn3view0  

---

## Что ещё можно улучшить

| Улучшение | Когда пригодится |
|-----------|------------------|
| **AttributeGen** вместо Lua | Если нужна только передача значения дальше без логики — фильтр `istio.filters.http.attribute_gen` проще и надёжнее. Пример формирует тот же заголовок <br/>```yaml\n    name: istio.filters.http.attribute_gen\n    typed_config:\n      \"@type\": type.googleapis.com/istio.telemetry.AttributeGen\n      attributes:\n        request.headers.x-client-cn:\n          string_value: \"%DOWNSTREAM_PEER_SUBJECT%\"\n``` | citeturn9view0turn8search2 |
| **Метрика Prometheus** | Через `handle:counter("missing_peer_cert"):increment(1)` фиксировать процент запросов без сертификата. citeturn2view0 |
| **unit-тесты Lua** | Скрипт можно завернуть в отдельный файл, подключать через `source_codes` и тестировать `ssl_mock`-объектом. |

---

### Проверка перед выкладкой

1. `istioctl analyze -f envoyfilter.yaml` — отсутствие ошибок IST0151/155.  
2. В k8s-кластер:  
   ```bash
   kubectl apply -f envoyfilter.yaml
   kubectl -n istio-system rollout status deployment/istio-ingressgateway
   ```  
3. Тест:  
   ```bash
   curl --resolve stack17.app.crds.asm-uk-cdc-01.uat.fichc.intranet.db.com:443:INGRESS_IP \
        --cert client.pem --key client-key.pem https://stack17.app... -v | grep x-client-cn
   ```  

После этих шагов фильтр надёжен, воспроизводим и готов к работе в production.
