**Коротко:** `istioctl proxy-config endpoints …` выводит список адресов, которые Envoy-в-шлюзе получил от Istiod (EDS). Если список пуст, шлюз **знает о кластере, но не получил ни одного «здорового» адреса**. Это почти всегда означает одну из пяти вещей:

1. у Kubernetes-Service нет готовых Pod’ов (или селектор не совпадает); 2) порт сервиса не помечен как HTTP (`name: http-…`); 3) VirtualService ссылается на подмножеcтво (*subset*) или FQDN, для которого Endpoints не формируются; 4) Service находится в другом namespace; 5) Pods помечены `NotReady`, поэтому Istio не публикует их в EDS. Ниже пошагово проверяем каждую гипотезу.

---

## 1 Проверяем, что Kubernetes вообще отдаёт Endpoints

```bash
kubectl -n minio get endpoints minio-console -o wide
```

*Если список `Subsets: <none>`* — селектор Service не совпадает с метками Pod’ов или Pods ещё не готовы; Envoy в этом случае также покажет пустой список, что и вызывает 503 *no healthy upstream* ([stackoverflow.com][1]).

Если IP-адреса есть, переходим к шагу 2.

---

## 2 Service-порт должен называться `http-*`

Istio обрабатывает L7-маршрутизацию **только** для портов, чьё имя начинается с `http`, `http2`, `grpc` и т.д.; иначе поток считается «сырой» TCP и в EDS публикуется другой кластер, к которому Gateway не маршрутизирует запросы ([stackoverflow.com][2]).

```yaml
ports:
- name: http-console       # правильно
  port: 9090
  targetPort: 9090
```

После изменения имени подождите \~30 с, пока Istiod отправит новое обновление.

---

## 3 Сравниваем FQDN/namespace в VirtualService

```yaml
route:
- destination:
    host: minio-console.minio.svc.cluster.local   # FQDN!
    port:
      number: 9090
```

Если VirtualService находится в другом namespace, короткое имя `minio-console` превратится в `minio-console.<vs-namespace>.svc.cluster.local`, и шлюз попросит EDS «левый» сервис, где эндпойнтов нет ([developers.redhat.com][3]).

---

## 4 Подмножества (subset) и DestinationRule

Когда в маршруте указано `subset: v1`, Envoy ищет кластер
`outbound|9090|v1|minio-console.…`. Если такого кластера нет или в нём нет адресов, `proxy-config endpoints` будет пуст, хотя дефолтный кластер с адресами существует ([stackoverflow.com][1]).

Проверьте:

```bash
istioctl proxy-config clusters <gw-pod> | grep minio-console
# а затем
istioctl proxy-config endpoints <gw-pod> \
  --cluster "outbound|9090|v1|minio-console.minio.svc.cluster.local"
```

Если подсет пуст — либо Pods не имеют метки `version: v1`, либо DestinationRule ошибочен.

---

## 5 Pods должны быть Ready

Istio удаляет адрес Pod’a из EDS, когда `readinessProbe` красная.
Типичный симптом: `kubectl get deploy` показывает `0/1 READY`, а шлюз отдаёт 503 ([stackoverflow.com][1], [developers.redhat.com][3]).

---

## 6 Команды для полной диагностики

| Цель                                          | Команда                                                                                                  |                      |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------- | -------------------- |
| Посмотреть, какой именно кластер ищет маршрут | \`istioctl proxy-config routes <gw-pod> --name https.443.\*                                              | jq\` ([istio.io][4]) |
| Убедиться, что шлюз синхронизирован с Istiod  | `istioctl proxy-status` — все столбцы `SYNCED` ([istio.io][4])                                           |                      |
| Проверить YAML на скрытые ошибки              | `istioctl analyze -A` — ловит 90 % проблем конфигурации ([istio.io][5])                                  |                      |
| Включить детальный лог шлюза                  | `curl -XPOST localhost:15000/logging?level=debug` и искать `upstream_reset` ([developers.redhat.com][3]) |                      |

---

## 7 Типичные сценарии, когда Endpoints пусты

| Причина                            | Как проявляется                                                                  | Решение                                                                |     |                                                                         |
| ---------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | --- | ----------------------------------------------------------------------- |
| Селектор Service не совпадает      | В объекте Endpoints нет IP                                                       | Исправить `spec.selector` у Service                                    |     |                                                                         |
| `subset` без соответствующих меток | Пусто только в кластере \`…                                                      | v1                                                                     | …\` | Добавить метку `version: v1` или убрать subset ([stackoverflow.com][1]) |
| Порт без `http-` префикса          | `proxy-config endpoints` для HTTP-кластера пуст, но для TCP-кластера есть адреса | Переименовать порт ([stackoverflow.com][2])                            |     |                                                                         |
| Pods `NotReady`                    | `READY 0/1` в `kubectl get deploy`                                               | Починить `readinessProbe` и логи приложения ([stackoverflow.com][1])   |     |                                                                         |
| Namespace/FQDN ошибка              | Кластер начинается не на `minio-console.minio…`                                  | Использовать полный FQDN в VirtualService ([developers.redhat.com][3]) |     |                                                                         |

---

## 8 Что сделать прямо сейчас

1. **`kubectl get endpoints`** — подтверждаем, что адреса реально есть.
2. Если есть → **переименуйте порт в `http-console`** (если ещё не).
3. **Проверьте `cluster` и `subset`** через `istioctl proxy-config clusters`.
4. **Почините readiness-probe**, если Pods не готовы.
5. Перепроверьте VirtualService: host, namespace, subset.

После того как в выводе

```bash
istioctl proxy-config endpoints <gw-pod> \
  --cluster "outbound|9090||minio-console.minio.svc.cluster.local"
```

появятся строки с `HEALTHY`, ошибка 503 исчезнет. Удачи!

[1]: https://stackoverflow.com/questions/47664397/istio-ingress-resulting-in-no-healthy-upstream "kubernetes - Istio Ingress resulting in \"no healthy upstream\" - Stack Overflow"
[2]: https://stackoverflow.com/questions/54538510/istio-pilot-is-creating-tcp-listeners-that-should-be-http "kubernetes - Istio Pilot is creating TCP Listeners that should be HTTP - Stack Overflow"
[3]: https://developers.redhat.com/articles/2022/12/23/troubleshooting-no-healthy-upstream-errors-istio-service-mesh "Troubleshooting \"no healthy upstream\" errors in Istio service mesh | Red Hat Developer"
[4]: https://istio.io/latest/docs/ops/diagnostic-tools/proxy-cmd/ "Istio / Debugging Envoy and Istiod"
[5]: https://istio.io/latest/docs/ops/common-problems/validation/?utm_source=chatgpt.com "Configuration Validation Problems - Istio"
