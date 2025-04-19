### Что именно происходит  

`curl` успевает открыть TCP‑соединение с `192.168.105.4:443`, посылает ClientHello, после чего получает **RST**.  
Envoy‑прокси в `istio-ingressgateway` обычно сбрасывает TLS‑сеанс, когда:

| Причина | Симптом | Как проверить |
|---|---|---|
| 1. На порту 443 нет слушателя | RST ещё до начала TLS, либо `ss -lnt` внутри пода не показывает `443` | `kubectl -n istio-system get svc istio-ingressgateway -o yaml` – должен быть порт `443` → `targetPort: 8443` |
| 2. Gateway не описывает сервер `HTTPS` | В конфиг‑дампе нет listener`‑443` | `kubectl -n istio-system get gateway -o yaml` |
| 3. Ingress‑gateway не может прочитать Secret с сертификатом | RST сразу после ClientHello, в логах ingress‑gateway видно `SecretFetcher` / `Failed to fetch secret` | `kubectl -n istio-system logs -l istio=ingressgateway -c istio-proxy | grep -i secret` |

Чаще всего в домашних кластерах виноват пункт **3** – секрет находится **не** в `istio-system` или у service‑account нет прав на его чтение. При такой ситуации получаете именно «connection reset by peer» без каких‑либо сообщений в логе приложения citeturn1view0; аналогичный кейс описан в issue citeturn2view0.

---

### Проверяем шаг за шагом

1. **Сервис LoadBalancer**  
   ```bash
   kubectl -n istio-system get svc istio-ingressgateway -o wide
   # В столбцах PORT(S) должно быть 80:****/TCP,443:****/TCP
   ```
2. **Gateway**  
   ```bash
   kubectl -n istio-system get gateway YOUR‑GATEWAY -o yaml
   ```
   Ожидаем:
   ```yaml
   servers:
   - port:
       number: 443
       name: https
       protocol: HTTPS
     tls:
       mode: SIMPLE
       credentialName: httpbin‑lima‑cert   # <‑ имя секрета
     hosts:
     - httpbin.lima
   ```
3. **Секрет с TLS**  
   ```bash
   kubectl -n istio-system get secret httpbin-lima-cert -o yaml
   # labels: istio.io/key-and-cert: "true" (необязательно, но полезно)
   # должен содержать: data/tls.crt и data/tls.key
   ```
   > Если секрета нет, а он лежит, например, в `default`, Ingress его прочитать не может – ровно та ситуация, когда Envoy сбрасывает соединение.

4. **Права доступа**  
   ```bash
   kubectl -n istio-system auth can-i get secret \
     --as system:serviceaccount:istio-system:istio-ingressgateway
   # должен вернуть yes
   ```

---

### Быстрый способ починить

```bash
# 1.  Пересоздаём сертификат прямо в  istio-system
kubectl -n istio-system apply -f - <<'EOF'
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: httpbin-lima-cert
  namespace: istio-system
spec:
  secretName: httpbin-lima-cert      # совпадает с credentialName
  commonName: httpbin.lima
  dnsNames:
  - httpbin.lima
  issuerRef:
    name: my-root-issuer             # ваш Issuer
    kind: Issuer
EOF
# 2.  Убеждаемся, что secret появился
kubectl -n istio-system get secret httpbin-lima-cert
# 3.  Перезапускаем pod ingress‑gateway, чтобы он забрал новый cert
kubectl -n istio-system rollout restart deploy/istio-ingressgateway
```

После перезапуска:

```bash
curl -v --resolve httpbin.lima:443:192.168.105.4 https://httpbin.lima/status/200
# <- должен вернуть 200 OK с  сертификатом, выданным вашим CA
```

---

### Если всё ещё не работает

* Выложите сюда YAML `Gateway` и `VirtualService`.
* Покажите вывод  
  `istioctl proxy-config secret -n istio-system $(kubectl get pod -n istio-system -l istio=ingressgateway -o=jsonpath='{.items[0].metadata.name}')` – он сразу покажет видит ли Envoy секрет.
* Убедитесь, что сервис `httpbin` действительно слушает тот порт, который указан в `VirtualService` (по умолчанию `8000`).

Следуя этим шагам вы в 99 % случаев находите ошибку конфигурации и избавляетесь от «connection reset by peer». Если потребуется – пришлите выводы команд, посмотрим дальше.
