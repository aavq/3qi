Думал на протяжении 5 секунд


### Ключевая мысль

`token_secret.sds_config.path` — это **путь к ОДНОМУ файлу**, в котором Envoy-SDS ищет описание секрета в формате YAML. Сейчас вы подключаете **каталог** `/etc/istio/creds/token-secret.yaml/`, а не файл, поэтому Envoy не находит нужный объект и выдаёт ошибку. Ниже показано:

* как правильно сформировать файл-секрет с `CLIENT_SECRET` (и, при необходимости, HMAC-ключом);
* как упаковать его в Kubernetes-Secret;
* как смонтировать его в sidecar **istio-proxy** так, чтобы внутри действительно появился файл `/etc/istio/creds/token-secret.yaml`;
* когда вообще нужен HMAC-секрет.

---

## 1 Что именно ожидает Envoy

Спецификация фильтра OAuth2 требует, чтобы в файле находилась структура SDS-секрета вида:

```yaml
# token-secret.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: token                         # должно совпадать с credentials.token_secret.name
  generic_secret:
    secret:
      inline_string: 1BimnZK1GlQ08UFV9xiSlKqVHDQU2vvN%
```

Если нужен HMAC-ключ для cookie-подписи (**HS256**), создайте второй файл `hmac.yaml`:

```yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: hmac                         # совпадает с credentials.hmac_secret.name
  generic_secret:
    secret:
      inline_string: 70feb9334fb76a34c08b470b6c848c8af4600fed11f24b0fed4336f27363e09b
```

---

## 2 Создаём Kubernetes-Secret с правильными именами файлов

```bash
kubectl -n default create secret generic envoy-oauth-secrets \
  --from-file=token-secret.yaml \
  --from-file=hmac.yaml
```

Опция `--from-file` сохраняет точные имена файлов внутри тома.

---

## 3 Монтируем файлы в **istio-proxy**

Добавьте аннотации в шаблон Pod’а (Deployment/StatefulSet):

```yaml
template:
  metadata:
    annotations:
      sidecar.istio.io/userVolume: |
        [{
          "name": "oauth-secrets",
          "secret": {                 # ВАЖНО: вложенный объект secret:{}
            "secretName": "envoy-oauth-secrets"
          }
        }]
      sidecar.istio.io/userVolumeMount: |
        [{
          "name": "oauth-secrets",
          "mountPath": "/etc/istio/creds",
          "readOnly": true
        }]
```

* Весь Secret монтируется каталогом `/etc/istio/creds`
  ├── `token-secret.yaml`
  └── `hmac.yaml`

Перезапустите Deployment:

```bash
kubectl rollout restart deploy/httpbin
```

---

## 4 Правим EnvoyFilter

```yaml
credentials:
  client_id: httpbin-frontend
  token_secret:
    name: token
    sds_config:
      path: /etc/istio/creds/token-secret.yaml   # путь к файлу, а не каталогу
  hmac_secret:          # уберите целиком, если остаетесь на RS256
    name: hmac
    sds_config:
      path: /etc/istio/creds/hmac.yaml
  cookie_domain: ".lima"
  cookie_names:
    bearer_token: BearerToken
    oauth_hmac:  OauthHMAC
    oauth_expires: OauthExpires
```

---

## 5 Проверка

```bash
# в sidecar
kubectl exec -c istio-proxy -it pod/httpbin-xxx -- ls /etc/istio/creds
# token-secret.yaml  hmac.yaml

# логи Envoy
kubectl logs pod/httpbin-xxx -c istio-proxy | grep virtualInbound
# ошибок о «does not exist» быть не должно
```

---

## 6 Нужен ли HMAC-секрет?

| Сценарий                                                                   | Нужен `hmac_secret`?                                                                                                           |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Keycloak выпускает токены **RS256** (по умолчанию)                         | **Нет.** Фильтр сам создаёт HMAC-cookie.                                                                                       |
| Вы переключились на **HS256** и хотите собственный ключ для подписи cookie | **Да.** Добавьте `hmac.yaml`, пропишите блок `hmac_secret` и используйте тот же ключ во всех сервисах, которые проверяют HMAC. |

---

### Итог

* `sidecar.istio.io/userVolume` должен содержать полный объект `secret:{ secretName: ... }`; иначе том не создаётся.
* `path:` в `sds_config` всегда указывает на файл, а не каталог.
* Для RS256 достаточно одного файла `token-secret.yaml`; `hmac.yaml` можно опустить.

После исправлений файлы появятся в sidecar, Envoy загрузит их без ошибок LDS, и OAuth2-фильтр заработает.


```yaml
spec:
  template:
    metadata:
      annotations:
        sidecar.istio.io/userVolume: |
          [{
          "name": "oauth-secrets",
          "secret": {
              "secretName": "envoy-oauth-secrets"
          }
          }]
        sidecar.istio.io/userVolumeMount: |
          [{
          "name": "oauth-secrets",
          "mountPath": "/etc/istio/creds",
          "readOnly": true
          }]
```
