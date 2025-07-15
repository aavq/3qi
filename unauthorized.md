**После того как OIDC‑логин прошёл без `redirect_uri_mismatch`, Kiali уже принимает ID‑токен, но падает на **авторизации**.
Это бывает в двух ситуациях:

| Сценарий                                                           | Что починить                                                                                                                                                                  |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Кластер не умеет принимать ваш OIDC‑токен**                      | В Kiali установите `disable_rbac: true` – тогда Kiali не будет обращаться к API‑серверу от вашего имени, и любой аутентифицированный пользователь сразу попадёт в UI          |
| **Кластер принимает OIDC‑токены, но у пользователя нет RBAC‑прав** | Добавьте правильные `ClusterRoleBinding/RoleBinding` к тем же User/Group claim‑ам, что приходят в ID‑токене, или создайте отдельную группу в AD и свяжите её с `kiali-viewer` |

Ниже – как определить, какая из двух причин у вас и что именно прописать.

---

## 1 Проверяем логи Kiali

```bash
kubectl logs -n kiali deploy/kiali --since=5m | grep -E "(Unauthorized|cannot list|failure when retrieving user)"
```

* `failure when retrieving user identity` / `401 Unauthorized` ⇒ кластер **не** доверяет токену – лечим *вариантом A* ([GitHub][1])
* `User "<адрес‑почты>" cannot list namespaces` / `Forbidden` ⇒ нет RBAC‑прав – лечим *вариантом B* ([pre-v1-41.kiali.io][2])

---

## 2 Вариант A — кластеру не нужен RBAC (быстрое решение)

1. В CR/ConfigMap Kiali добавьте:

   ```yaml
   spec:
     auth:
       strategy: openid
       openid:
         client_id: "kiali-client"
         issuer_uri:  "https://<issuer>"
         disable_rbac: true        # <- ключевая строка
         username_claim: email
         scopes: ["openid","email"]
   ```

   Поле `disable_rbac` полностью отключает namespace‑access‑control, и Kiali больше не разговаривает с API‑сервером от лица пользователя ([kiali.io][3]).

2. Перезапустите pod: `kubectl rollout restart deploy/kiali -n kiali`.

Теперь любой пользователь, прошедший OIDC‑логин, попадает в Kiali с кластерными правами **view only**.

> Минус – у всех одинаковые права. Если нужно разграничение по пользователям/группам, переходите к варианту B.

---

## 3 Вариант B — включаем Namespace / Cluster RBAC

### 3.1 Убедитесь, что API‑сервер принимает ваш ID‑токен

* Параметры запуска должны совпадать с настройками Kiali:
  `--oidc-issuer-url=https://<issuer>` и `--oidc-client-id=<client_id>` ([Kubernetes][4]).
* `username_claim` в Kiali должен = `--oidc-username-claim` (часто `email` или `preferred_username`) ([kiali.io][3]).

Если у вас управляемый кластер (EKS, GKE, AKS) – проверьте, поддерживает ли он собственный OIDC; для AKS есть известное ограничение, требующее `kube-oidc-proxy` ([Google Groups][5]).

### 3.2 Посмотрите, какие claims прилетают

```bash
# копируем id_token из браузера и декодируем:
jwt-decode() { jq -R 'split(".")|.[1]|@base64d|fromjson' <<<"$1"; }
jwt-decode $ID_TOKEN | jq '{sub, email, groups}'
```

Простой однострочник для shell показан в функции gist ([Gist][6]).

### 3.3 Давайте права

* **Минимум, чтобы зайти** – право `get namespaces` ([pre-v1-41.kiali.io][2])
* **Полноценный read‑only UI** – воспользуйтесь готовым `ClusterRole kiali-viewer` и свяжите его с пользователем или группой:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kiali-viewer-users
subjects:
- kind: User              # или Group, если в токене есть claim "groups"
  name: ivan.petrov@corp.com   # либо AD‑группа, например "mesh‑observers"
roleRef:
  kind: ClusterRole
  name: kiali-viewer
  apiGroup: rbac.authorization.k8s.io
```

*Если хотите давать доступ только к определённым неймспейсам – создайте обычный `RoleBinding` в каждом из них* ([kiali.io][7]).

### 3.4 Проверяем

```bash
kubectl auth can-i list deployments --as=ivan.petrov@corp.com
```

Должно вернуть `yes`.
После этого перезапустите Kiali и зайдите снова.

---

## 4 Частые вопросы

| Проблема                                                       | Причина                                                         | Решение                                                                                                   |
| -------------------------------------------------------------- | --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| После логина 401 JSON: `failure when retrieving user identity` | Kiali использует **другой** client\_id, чем API‑сервер          | Перенастройте Kiali на тот же client\_id, который указан в `--oidc-client-id` API‑сервера ([kiali.io][3]) |
| UI открыт, но namespace list пуст                              | У пользователя нет `get namespaces`                             | Добавьте минимальную Role/Binding, как в 3.3                                                              |
| Токен не содержит `groups`                                     | IdP не выдаёт claim                                             | В OIDC‑клиенте добавьте scope `groups` (или в Azure – `api_token: access_token`) ([kiali.io][3])          |
| На AKS/OIDC всё равно 401                                      | Известный баг интеграции от AKS                                 | Используйте `kube-oidc-proxy` или отключайте RBAC в Kiali ([Google Groups][5])                            |
| Надо ограничить доступ доменом                                 | Используйте `allowed_domains` список в Kiali CR ([kiali.io][3]) |                                                                                                           |

---

## 5 Итого

* **Нет планов на per‑user RBAC →** ставьте `disable_rbac: true` – самый быстрый путь к рабочему UI.
* **Нужен контроль доступа →**

  1. убедитесь, что API‑сервер принимает токены (параметры `--oidc-*`),
  2. настройте одинаковые `client_id`/`issuer_uri` в Kiali и кластере,
  3. выдайте нужным User/Group claim‑ам роль `kiali-viewer` (или свою) через RoleBinding/ClusterRoleBinding.
* После любого изменения перезапускайте pod `kiali`, чтобы он перечитал конфигурацию и секрет.

Следуя этим шагам, OIDC‑логин завершится успешной авторизацией, а Kiali перестанет показывать ошибку доступа.

[1]: https://github.com/kiali/kiali/issues/3262?utm_source=chatgpt.com "Fail to login with OpenID Connect as \"failure when retrieving user ..."
[2]: https://pre-v1-41.kiali.io/documentation/v1.41/configuration/rbac/ "Kiali: Service mesh observability and configuration"
[3]: https://kiali.io/docs/configuration/authentication/openid/ "OpenID Connect strategy | Kiali"
[4]: https://kubernetes.io/docs/reference/access-authn-authz/authentication/?utm_source=chatgpt.com "Authenticating | Kubernetes"
[5]: https://groups.google.com/g/kiali-dev/c/L0O09jgN4y4?utm_source=chatgpt.com "Need help with KIALI OpenId with RBAC on AKS clusters"
[6]: https://gist.github.com/angelo-v/e0208a18d455e2e6ea3c40ad637aac53?utm_source=chatgpt.com "Decode a JWT via command line - GitHub Gist"
[7]: https://kiali.io/docs/configuration/rbac/ "Namespace access control | Kiali"
