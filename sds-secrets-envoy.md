**Разбор проблемы с конфигурацией SDS**

Пользователь столкнулся с трудностями при настройке пути конфигурации SDS для токен-секрета в фильтре Envoy в Istio. Они подключают секрет в директорию, но фильтр ожидает путь к файлу. Видимо, SDS ожидает, что в указанном файле будет сам секрет, а не директория с ключами. Необходимо уточнить, что SDS требует путь к файлу, содержащему секрет в формате YAML или JSON, а не содержимое директории.

**Решение проблемы с монтированием токена**

Пользователь столкнулся с проблемой, когда секрет не может быть правильно смонтирован, так как фильтр ожидает файл, а не директорию. Решение: создать секрет с ключом token-secret.yaml и монтировать его в /etc/istio/creds. Для этого используется Kubernetes volumes и userVolumeMount с указанием правильного пути для файла. Важно правильно настроить подмонтирование и аннотации для корректного получения секретов через SDS.


**Объяснение настройки SDS**

Путь к секрету токен должен быть файлом, а не директорией. Поэтому, нужно использовать отдельный секрет с ключом token-secret.yaml или просто ключом token-secret с указанием пути. Путь sds\_config должен указывать на директорию, содержащую файл секрета, но из-за ошибки с несуществующим путем, лучше смонтировать секрет прямо по пути файла. В Istio EnvoyFilter можно использовать конфигурацию вида: `{token_secret: {name: idp-token, sds_config: {path: /etc/istio/creds/token-secret.yaml}}}`.


**Подготовка объяснения с примерами кода**

Необходимо собрать источники для цитирования при создании ответа:

* Документация по Kubernetes секретам, Istio аннотациям и фильтру OAuth в Envoy.
* Примеры из Istio по монтированию sidecar.
* Описание ошибки с загрузкой секрета и пути к файлу в Istio.
* Предпочтительное использование пути к файлу, а не директории.

Алгоритм устранения ошибки: переделать путь монтирования как путь к директории, а не к файлу, и использовать ключ для токена.


Думал на протяжении 1m 36s


**Ключевая мысль** `token_secret.sds_config.path` — это **путь до ОДНОГО файла**, в котором Envoy-SDS найдёт описания секрета (ов) в YAML-формате.
Сейчас вы монтируете *каталог* `/etc/istio/creds/token-secret.yaml/`, а не файл, поэтому Envoy ломается. Ниже показано:

* как сформировать файл-секрет с `CLIENT_SECRET` (и при желании HMAC-ключом),
* как поместить его в Kubernetes `Secret`,
* как смонтировать так, чтобы внутри **istio-proxy** действительно существовал файл
  `/etc/istio/creds/token-secret.yaml`,
* когда HMAC вообще нужен.

---

## 1 Что именно ожидает Envoy

Спецификация OAuth2-фильтра требует, чтобы в файле стояла структура SDS-`Secret`(ов) — пример прямо в документации([Envoy Proxy][1]).
Если вы хотите хранить токен и HMAC по отдельным файлам, GitHub-issue поясняет, что это допустимо и даже проще([GitHub][2]).

```yaml
# token-secret.yaml  (1-й файл)
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: token
  generic_secret:
    secret:
      inline_string: 1BimnZK1GlQ08UFV9xiSlKqVHDQU2vvN%

# hmac.yaml         (2-й файл, если нужен HS256-cookie)
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: hmac
  generic_secret:
    secret:
      inline_string: <your-hmac-key-base64>
```

---

## 2 Создаём Kubernetes `Secret` с правильными именами файлов

```bash
# token + hmac в одном объекте
kubectl -n default create secret generic envoy-oauth-secrets \
  --from-file=token-secret.yaml \
  --from-file=hmac.yaml
```

*Флаги `--from-file` сохраняют точное имя файла внутри Volume*([Kubernetes][3]).

---

## 3 Монтируем файлы в **istio-proxy**

Istio позволяет добавить собственные тома в sidecar через аннотации
`sidecar.istio.io/userVolume` и `sidecar.istio.io/userVolumeMount`([Istio][4]).

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: httpbin
spec:
  template:
    metadata:
      annotations:
        sidecar.istio.io/userVolume: |
          [{
            "name":"oauth-secrets",
            "secretName":"envoy-oauth-secrets"
          }]
        sidecar.istio.io/userVolumeMount: |
          [{
            "name":"oauth-secrets",
            "mountPath":"/etc/istio/creds",
            "readOnly":true
          }]
```

* Весь секрет монтируется каталогом **/etc/istio/creds**
  └── token-secret.yaml
  └── hmac.yaml
* Такой же приём использует официальный пример TLS-терминации в sidecar’е([Istio][5]).

---

## 4 Правим EnvoyFilter (фрагмент)

```yaml
credentials:
  client_id: httpbin-frontend
  token_secret:
    name: token              # ← имя SDS-ресурса
    sds_config:
      path: /etc/istio/creds/token-secret.yaml
  hmac_secret:                # ⚠︎ только если нужен HS256-cookie
    name: hmac
    sds_config:
      path: /etc/istio/creds/hmac.yaml
```

> ⚠︎ **Путь указывает именно на файл**, поэтому каталогом быть перестаёт.

После `kubectl apply` Envoy-sidecar перечитает LDS и файл найдётся — ошибки `virtualInbound … does not exist` исчезнут (убедитесь в логах)([GitHub][6]).

---

## 5 Нужен ли HMAC-секрет?

| Сценарий                                                                                                                                          | Нужен `hmac_secret`?                                                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Оставляете подпись токенов **RS256** (дефолт Keycloak) — cookies кодируются HMAC-SHA внутри фильтра, а валидация JWT идёт по открытым ключам JWKS | **Нет** — HMAC генерируется фильтром; дополнительный ключ не нужен([Envoy Proxy][1])                                                                                              |
| Переключаете Keycloak/клиент на **HS256** и хотите явно задавать соль для cookie-HMAC                                                             | **Да** — создайте `hmac.yaml` c секретом и пропишите его, как показано выше; тот же ключ понадобится в каждом сервисе, если сами будете проверять cookie подпись([Kubernetes][7]) |

Большинство production-инсталляций остаётся на RS256, потому что он не требует распределять симметричный ключ по сервисам и упрощает ротацию сертификатов.

---

## 6 Проверяем

```bash
# внутри sidecar
kubectl exec -n default -it <pod> -c istio-proxy -- \
  ls -l /etc/istio/creds

# ↳ token-secret.yaml  hmac.yaml
kubectl exec -n default -it <pod> -c istio-proxy -- \
  grep inline_string /etc/istio/creds/token-secret.yaml
```

Повторите запрос к приложению; в логах **istio-proxy** больше нет сообщений о потерянном пути — значит SDS-секрет подгружен и OAuth-фильтр работает.

---

## 7 Полезные ссылки

1. Kubernetes Secrets — использование как файлы
2. Kubernetes Volumes — маппинг с `items` для переименования файлов
3. Annotations `sidecar.istio.io/userVolume*` — справка Istio
4. Официальный пример Istio «Ingress sidecar TLS termination» с аннотациями
5. Док Envoy OAuth2-фильтра: формат `token_secret` / `hmac_secret` и образец файла
6. Issue про отдельные файлы и форму секрета (clarification)
7. История «secret load issue» (#39545) — подтверждает, что путь должен вести к файлу
8. Issue «OAuth2 filter not applied» (#43251) — аналогичная ошибка при неверном `path`
9. Best-practice : HMAC не нужен при RS256 (Kubernetes good practices on Secrets)
10. Док по **Projected volumes** — один объект Secret → несколько файлов

Исправив монтирование и убедившись, что пути указывают на настоящие файлы, вы устраните ошибку LDS, и Envoy-OAuth конфигурация будет полностью рабочей.

[1]: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/oauth2_filter?utm_source=chatgpt.com "OAuth2 — envoy 1.35.0-dev-7ec20a documentation"
[2]: https://github.com/envoyproxy/envoy/issues/13736?utm_source=chatgpt.com "Question about how to use envoy Oauth2 · Issue #13736 - GitHub"
[3]: https://kubernetes.io/docs/concepts/configuration/secret/?utm_source=chatgpt.com "Secrets | Kubernetes"
[4]: https://istio.io/latest/docs/reference/config/annotations/?utm_source=chatgpt.com "Resource Annotations - Istio"
[5]: https://istio.io/latest/docs/tasks/traffic-management/ingress/ingress-sidecar-tls-termination/?utm_source=chatgpt.com "Ingress Sidecar TLS Termination - Istio"
[6]: https://github.com/istio/istio/issues/39545?utm_source=chatgpt.com "Unable to use oauth2 proxy via EnvoyFilter; secret load issue #39545"
[7]: https://kubernetes.io/docs/concepts/security/secrets-good-practices/?utm_source=chatgpt.com "Good practices for Kubernetes Secrets"
