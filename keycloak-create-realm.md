Думал на протяжении 35 секунд


В кратком изложении: чтобы приложение внутри вашего нового Keycloak-реалма успешно работало по OAuth 2.0, достаточно (1) создать или выбрать реалм, (2) прописать публичный фронт-енд-URL `https://idp.lima`, (3) завести клиента OIDC и добавить в его **Redirect URI** значение `https://idp.lima/*` либо более точный путь (`/callback`, `/oauth2/callback` и т. д.). Ниже приведена подробная пошаговая инструкция как сделать это в новой Web-консоли (Keycloak ≥ 24) и альтернативный способ через CLI `kcadm.sh`.

---

## 1 Перед началом

* Войдите в админ-консоль по адресу `https://idp.lima/admin/` под учёткой **admin** / `AdminP@ssw0rd`.
* Убедитесь, что сервер запущен в «optimized mode» и видит правильный `hostname-url` (в меню **Server info → Host**). ([Keycloak][1])

---

## 2 Создаём (или выбираем) Realm

1. В левом верхнем выпадающем списке нажмите **Create realm**.
2. Заполните поле **Realm name**, например `demo`, и нажмите **Create**. ([Keycloak][2])
3. Откройте в боковом меню **Realm settings → General**.

### 2.1 Настройка Frontend URL

* В новой UI параметр называется **Frontend URL**; заполните его значением `https://idp.lima`. Это заставит Keycloak формировать все внешние ссылки (в т. ч. ссылки на JS/CSS консоли) с нужным протоколом и хостом. ([Keycloak][3])
* Нажмите **Save**.

> **Совет.** Если вы оставите поле пустым, Keycloak будет строить абсолютные URL по заголовкам `X-Forwarded-*`; при смене протокола с HTTP на HTTPS могут появляться ошибки “invalid redirect\_uri”. ([GitHub][4])

---

## 3 Создаём OAuth 2.0-клиент

### 3.1 Через веб-консоль

1. Откройте **Clients → Create client**.
2. Заполните:

| Поле                      | Значение                                        | Комментарий                               |
| ------------------------- | ----------------------------------------------- | ----------------------------------------- |
| **Client type**           | *OpenID Connect*                                | Протокол OAuth 2.0/OIDC                   |
| **Client ID**             | `my-test-app`                                   | Любой уникальный идентификатор            |
| **Client authentication** | *On* для «confidential» (сервер), *Off* для SPA | опционально                               |
| **Standard flow**         | ✅                                               | включает кодовый поток Authorization Code |
| **Direct access grants**  | при необходимости                               | парольный поток                           |
| **Root URL**              | `https://idp.lima`                              | базовый URL приложения                    |

3. Нажмите **Next** → **Save**.	New UI перенесёт вас на вкладку **Settings** клиента ([Medium][5]).

#### 3.1.1 Redirect URIs

* В блоке **Valid redirect URIs** нажмите **+**, введите:

```
https://idp.lima/*
```

или конкретный путь:

```
https://idp.lima/callback
```

* Добавьте то же значение в **Web origins**.
* Сохраните изменения. ([Stack Overflow][6])

### 3.2 Через CLI `kcadm.sh`

```bash
# Логинимся в Keycloak
/opt/keycloak/bin/kcadm.sh config credentials \
  --server https://idp.lima \
  --realm master \
  --user admin \
  --password 'AdminP@ssw0rd'

# Создаём реалм (если нужно)
kcadm.sh create realms -s realm=demo -s enabled=true

# Создаём клиента public (SPA) в реалме demo
kcadm.sh create clients -r demo \
  -s clientId=my-test-app \
  -s publicClient=true \
  -s standardFlowEnabled=true \
  -s rootUrl='https://idp.lima' \
  -s redirectUris='["https://idp.lima/*"]' \
  -s webOrigins='["https://idp.lima"]'
```

CLI даёт ту же конфигурацию, что и UI, и полезен для автоматизации. ([Gist][7])

---

## 4 Проверка

```bash
# Авторизационный запрос
https://idp.lima/realms/demo/protocol/openid-connect/auth\
?client_id=my-test-app\
&redirect_uri=https%3A%2F%2Fidp.lima%2Fcallback\
&response_type=code\
&scope=openid%20profile
```

* В браузере появится страница логина; после ввода учётных данных Keycloak перенаправит обратно на `https://idp.lima/callback?code=...`.
* Если видите ошибку «Invalid parameter: redirect\_uri», проверьте, что значение точь-в-точь совпадает с добавленным в клиент. ([Stack Overflow][6])

---

## 5 Дополнительные настройки клиента

| Вкладка                                                    | Что настраивается                      | Когда нужно                   |
| ---------------------------------------------------------- | -------------------------------------- | ----------------------------- |
| **Credentials**                                            | Секрет клиента (для confidential-flow) | Backend-приложения            |
| **Client scopes**                                          | Стандартные/пользовательские scopes    | Ограничение выданных claims   |
| **Mapper**                                                 | Доп. атрибуты в ID-токен               | Добавление ролей, email и др. |
| **Advanced settings → Proof Key for Code Exchange (PKCE)** | Включить **S256**                      | Мобильное/SPA приложение      |

Документация по каждому разделу доступна в официальном *Server Admin Guide* и *Securing Applications Guide*. ([Keycloak][3], [Keycloak][8], [Keycloak][9])

---

## 6 Частые ошибки и советы

* **HTTP → HTTPS-миграция**: всегда задавайте `Frontend URL` или `KC_HOSTNAME_URL`, иначе Keycloak продолжит строить ссылки на HTTP ([Keycloak][1]).
* **Wildcard `/*` в Redirect URIs**: удобно в DEV-среде, но в проде лучше указывать точные URI — это рекомендация RFC 8252 и команды Keycloak ([GitHub][4]).
* **SPA-клиенты**: ставьте `publicClient=true` (UI: выключите “Client authentication”) и включайте `PKCE` — так можно не хранить клиентский секрет на фронте. ([Keycloak][10])
* **Проверка discovery-документа**: `https://idp.lima/realms/demo/.well-known/openid-configuration` — убедитесь, что там правильные endpoints и `issuer`. ([Keycloak][9])

---

## 7 Что дальше

* Настройте **Service account roles** для back-channel запросов (Machine-to-Machine). ([GitHub][11])
* Изучите **Client Registration API** для self-service создания клиентов. ([Keycloak][10])
* Если планируете обновление Keycloak, смотрите раздел *Upgrading* перед миграцией, там описаны изменения в поведении redirect URI-валидации. ([Keycloak][12])

Следуя этим шагам, вы получите рабочий OAuth 2.0-клиент в реалме, который безопасно работает через публичный адрес `https://idp.lima`.

[1]: https://www.keycloak.org/server/hostname?utm_source=chatgpt.com "Configuring the hostname (v2) - Keycloak"
[2]: https://www.keycloak.org/getting-started/getting-started-zip?utm_source=chatgpt.com "OpenJDK - Keycloak"
[3]: https://www.keycloak.org/docs/latest/server_admin/index.html?utm_source=chatgpt.com "Server Administration Guide - Keycloak"
[4]: https://github.com/keycloak/keycloak/discussions/25684?utm_source=chatgpt.com "Incorrect redirect_uri · keycloak keycloak · Discussion #25684 - GitHub"
[5]: https://medium.com/keycloak/keycloak-new-ui-realm-client-configuration-b57baa9da9f4?utm_source=chatgpt.com "Keycloak New UI: Realm & Client Configuration. - Medium"
[6]: https://stackoverflow.com/questions/45352880/keycloak-invalid-parameter-redirect-uri?utm_source=chatgpt.com "keycloak Invalid parameter: redirect_uri - Stack Overflow"
[7]: https://gist.github.com/thomasdarimont/bb702bd1160eb200147cf1bee1c1f7ed?utm_source=chatgpt.com "kcadm example snippets - GitHub Gist"
[8]: https://www.keycloak.org/docs/25.0.6/securing_apps/index.html?utm_source=chatgpt.com "Securing Applications and Services Guide - Keycloak"
[9]: https://www.keycloak.org/securing-apps/oidc-layers?utm_source=chatgpt.com "Secure applications and services with OpenID Connect - Keycloak"
[10]: https://www.keycloak.org/securing-apps/client-registration?utm_source=chatgpt.com "Client registration service - Keycloak"
[11]: https://github.com/keycloak/keycloak/issues/29878?utm_source=chatgpt.com "Updating a client protocol mappers through Admi CLI (kcadm) resets ..."
[12]: https://www.keycloak.org/docs/latest/upgrading/index.html?utm_source=chatgpt.com "Upgrading Guide - Keycloak"
