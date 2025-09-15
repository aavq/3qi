
Похоже, речь про **Kiali** (наверное, опечатка «Kerali»). Симптомы «нет ни одного workload» + в логах «label … \[] not found» после апгрейда с 2.5 → 2.15 чаще всего сводятся к 3-м причинам:

1. **Сломалась модель видимости неймспейсов после перехода на Kiali v2**
2. **Несовпадение схемы меток `app`/`version` с тем, что ожидает Kiali**
3. **Недостаточные RBAC-права сервис-аккаунта Kiali**

Ниже — короткое объяснение «почему», как быстро проверить и что поправить.

---

# 1) Видимость неймспейсов в Kiali v2: что изменилось и где можно сломаться

С версии **Kiali 2.0** отменены старые ключи наподобие `deployment.accessible_namespaces` и `api.namespaces.*` — они **больше не поддерживаются**. Вместо них используется новая модель: **cluster-wide access** + **discovery selectors** (если хотите ограничивать видимость). По умолчанию Kiali в v2 имеет кластерный доступ и показывает все несистемные неймспейсы.

**Почему это важно именно у вас:**
Вы ставите Kiali **не через оператор**, а «вручную» (Deployment + ConfigMap). Настройки вроде `deployment.*` — это **поля CR оператора** и на «голый» сервер не действуют. Значит, видимость целиком зависит от **реальных RBAC-прав** сервис-аккаунта и от дефолтного поведения Kiali v2. Если при апгрейде вы оставили старые поля в ConfigMap или «урезали» права (или использовали `Role` вместо `ClusterRole`), Kiali банально не может читать ресурсы — и Workloads пустые.

**Что сделать: быстрая проверка**

```bash
# ВАЖНО: подставьте свой namespace и имя SA
kubectl auth can-i --as=system:serviceaccount:istio-system:kiali -A get pods
kubectl auth can-i --as=system:serviceaccount:istio-system:kiali -A list deployments
kubectl auth can-i --as=system:serviceaccount:istio-system:kiali -A watch namespaces
```

Все три должны вернуть **yes**. Если где-то **no** — это ваша первопричина.

**Минимально необходимый ClusterRole (пример)**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kiali-read-all
rules:
- apiGroups: [""]
  resources: ["pods","replicationcontrollers","services","endpoints","endpointslices","namespaces","nodes","configmaps"]
  verbs: ["get","list","watch"]
- apiGroups: ["apps"]
  resources: ["deployments","replicasets","statefulsets","daemonsets"]
  verbs: ["get","list","watch"]
- apiGroups: ["batch"]
  resources: ["jobs","cronjobs"]
  verbs: ["get","list","watch"]
- apiGroups: ["networking.istio.io","security.istio.io","gateway.networking.k8s.io"]
  resources: ["*"]
  verbs: ["get","list","watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kiali-read-all
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kiali-read-all
subjects:
- kind: ServiceAccount
  name: kiali
  namespace: istio-system
```

Такой кластерный бинд даёт доступ **во все текущие и будущие неймспейсы** без участия оператора — ровно то, что вы хотите. Документация подтверждает, что при установке не через оператор кластерный доступ обязателен.

---

# 2) Метки `app`/`version`: что поменялось и почему логи завалены «…labels not found»

Начиная с **Kiali 2.6**, дефолты `app_label_name`/`version_label_name` изменили на «unset», а Kiali **научился автоматически распознавать** несколько «стандартных пар» меток:

* `service.istio.io/canonical-name` + `service.istio.io/canonical-revision`
* `app.kubernetes.io/name` + `app.kubernetes.io/version`
* `app` + `version`
  (то есть можно **миксовать** эти схемы).

Однако, если у вас в кластере используются **нестандартные** ключи (например, `app_name`, `release`, `build`), то Kiali **не сможет собрать workload’ы** и вы увидите массовые предупреждения/валидации «у сабсета не найдены метки на matching host» (KIA0203) и похожие, т.к. Kiali не находит версии/приложения. Сам факт того, что вы видите в логах бесконечные жалобы на «labels … not found», очень хорошо стыкуется с этой проблемой.

**Что сделать: быстрая проверка**

```bash
# Посмотреть, какие метки реально есть на Подах:
kubectl get pods -A \
  -o custom-columns='NS:.metadata.namespace,POD:.metadata.name,app:.metadata.labels.app,ver:.metadata.labels.version,akn:.metadata.labels.app\.kubernetes\.io/name,akv:.metadata.labels.app\.kubernetes\.io/version,canon:.metadata.labels.service\.istio\.io/canonical-name,crev:.metadata.labels.service\.istio\.io/canonical-revision' \
  | head -30
```

Если столбцы `app`/`version` и `app.kubernetes.io/*`/canonical-\* пустуют — Kiali не сможет собрать Workloads.

**Варианты решения**

* Проще всего — **добавить** на Pod’ы одну из поддерживаемых пар меток (минимум `app` и, желательно, `version`) — это и Istio рекомендует.
* Или **явно указать** Kiali вашу кастомную схему меток в `config.yaml`:

  ```yaml
  istio_labels:
    app_label_name: "app.kubernetes.io/name"
    version_label_name: "app.kubernetes.io/version"
  ```

  (Эти ключи остались поддерживаемыми; если вы их задаёте, Kiali перестаёт «миксовать» и использует ровно то, что указано).

---

# 3) Случайно «выключили» все контроллеры

Kiali строит Workloads из Deployment/ReplicaSet/StatefulSet/DaemonSet (а RC/Job/CronJob по умолчанию **исключены** ради производительности). Если в `config.yaml` кто-то нечаянно сделал «минус все» в `kubernetes_config.excluded_workloads`, вы действительно увидите «пусто». Проверьте этот блок — по умолчанию туда попадают только RC/Job/CronJob.

---

# 4) Что именно означают ваши логи

Сообщения вида «subset’s labels are not found…» — это валидаторы Kiali (правило **KIA0203**): в `DestinationRule` определены `subsets`, но ни один Pod сервиса не имеет меток этого сабсета. Такое действительно «сыпется» лавиной, если Kiali не видит «правильные» пары меток приложения/версии (см. пункт 2). Это **симптом**, а не первопричина.

---

# 5) Чек-лист «разрулить за 10 минут»

1. **RBAC**: дайте kiali-SA кластерный read-only доступ (пример ClusterRole выше).
   Быстрый тест: `kubectl auth can-i --as=system:serviceaccount:… -A list pods` → **yes**.
2. **Метки**: обеспечьте наличие хотя бы одной поддерживаемой пары меток на Pod’ах (`app`+`version` / `app.kubernetes.io/name`+`…/version` / canonical-\*).
   Либо пропишите `istio_labels.*` в `config.yaml` под вашу схему.
3. **ConfigMap**: убедитесь, что в `kubernetes_config.excluded_workloads` вы случайно не исключили Deployment/StatefulSet/DaemonSet.
4. **Логи Kiali**: поднимите уровень логирования и проверьте стартовые строки — там видны применённые настройки (и ошибки прав/доступности).
5. (Опционально) **Prometheus** нужен для Graph/метрик, но не для списка Workloads. Если Workloads появятся, а граф останется пустым — уже смотреть `external_services.prometheus.*`.

---

## Готовый «минимальный» `config.yaml` для Kiali 2.15 (manual install), без оператора

> Работает при наличии ClusterRoleBinding как выше. Это безопасная база: workloads видны во всех неймспейсах, метки «миксуются» по умолчанию Kiali 2.6+, лишнего нет.

```yaml
server:
  port: 20001
auth:
  strategy: anonymous  # или ваш OpenID/SO
external_services:
  istio:
    istio_namespace: istio-system
  prometheus:
    url: "http://prometheus.istio-system:9090"  # при необходимости
kubernetes_config:
  # НЕ исключаем ключевые контроллеры:
  excluded_workloads:
    - "ReplicationController"
    - "Job"
    - "CronJob"
# Если у вас НЕ стандартные метки, раскомментируйте:
# istio_labels:
#   app_label_name: "app.kubernetes.io/name"
#   version_label_name: "app.kubernetes.io/version"
```

---

## Почему после апгрейда всё «вдруг» посыпалось?

* Вы перешли на ветку **Kiali v2**, где **устаревшие ключи** для неймспейсов полностью убраны.
* В **2.6** поменялась логика дефолтных меток (теперь по умолчанию Kiali «миксуёт» несколько пар) — это обнаруживает ошибки/нестандартные схемы ярче, чем раньше.
* Если права у kiali-SA были ограничены на уровне конкретных NS (через `Role`/`RoleBinding`), новая схема больше не «расширяется» оператором (вы его не используете), поэтому **новые неймспейсы** и правда не видны.

---

Если после применения RBAC и проверки меток список Workloads всё ещё пустой — дайте 2 вещи:

1. кусок вашего `config.yaml` Kiali;
2. выхлоп `kubectl auth can-i ...` из блока проверки.
   Разберём до винтика.



___


Отличные вопросы. Сведу всё, что важно для **Kiali 2.15** (ветка v2.x), с примерами и ссылками.

# 1) Какие поля **нельзя** держать в конфиге на v2.15

В v2.x Kiali окончательно отказался от старой модели «доступные/видимые неймспейсы» через include/exclude. Эти поля **удалены** и должны быть убраны из вашего `config.yaml` (или из CR, если вы когда-то мигрируете на оператор):

* `deployment.accessible_namespaces`
* `api.namespaces.include`
* `api.namespaces.exclude`
* `api.namespaces.label_selector_include`
* `api.namespaces.label_selector_exclude` ([Kiali][1])

Также в ветке 2.14+ появились новые «no longer used / auto-discovered» поля. Если вы когда-нибудь будете использовать **Kiali CR** (оператор), их нужно удалить именно из **CR** (в обычном `config.yaml` Kiali Server они и так не работают, но лучше не тащить мусорные ключи):

* (no longer used) `spec.istio_namespace`, `spec.in_cluster`, `spec.deployment.remote_secret_path`
* (auto-discovered, больше не задаются руками) `spec.external_services.istio.{config_map_name, istiod_deployment_name, istiod_pod_monitoring_port, envoy_admin_local_port, istio_canary_version, istio_injection_annotation, istio_sidecar_annotation, url_service_version}` ([Kiali][2])

Наконец, в v2.12 прекратилась поддержка старого графа Cytoscape и настройки
`kiali_feature_flags.ui_defaults.graph.impl` — её тоже не должно быть. ([Kiali][2])

# 2) Discovery selectors: какие значения, чтобы «видны все namespaces»

Поведение зависит от **cluster\_wide\_access**:

* **Самый простой и правильный для “все ns” способ при ручной установке (без оператора):**
  держите `deployment.cluster_wide_access: true` и **не задавайте** discovery selectors вовсе (или оставьте пустой список). Тогда Kiali покажет **все** неймспейсы, *кроме* системных (`kube-*`, `openshift-*`, `ibm-*`) — они специально скрываются по умолчанию. ([Kiali][1])

  Минимальный фрагмент `config.yaml`:

  ```yaml
  deployment:
    cluster_wide_access: true
  # discovery_selectors: []  # просто не указывайте
  ```

  (Так и делает официальный пример — `cluster_wide_access: true` в конфиге Kiali Server. ([GitHub][3]))

* **Если хотите видеть ещё и системные ns** — добавьте **label-based** селекторы, которые их включат:

  1. пометьте нужные системные ns меткой, например `kiali.io/visible=true`;
  2. добавьте селектор:

  ```yaml
  deployment:
    cluster_wide_access: true
    discovery_selectors:
      default:
        - matchLabels:
            kiali.io/visible: "true"
  ```

  Тогда Kiali перестанет использовать «исключение системных по умолчанию» и будет ровно следовать вашим селекторам. ([Kiali][1])

> Важно: **Kiali не использует** Istio discovery selectors. Если у Istio они настроены, обычно имеет смысл **синхронизировать** список и в Kiali вручную (через его discovery selectors), но это независимые механизмы. ([Kiali][1])

# 3) С чем взаимодействуют discovery selectors (логика и «подводные камни»)

* **`deployment.cluster_wide_access` (главное!)**

  * `true` (рекомендовано при ручной установке без оператора): Kiali имеет **кластерные** права. Discovery selectors в этом режиме работают как **фильтр видимости** (перформанс-оптимизация), а доступ остаётся кластерным. Пустой список ⇒ видны все несистемные ns. ([Kiali][1])
  * `false` (обычно только при установке через оператор): доступ даётся **только** на ns, совпавшие с discovery selectors (оператор создаёт Role/RoleBinding на каждый ns). Пустой список ⇒ доступны лишь ns Kiali и ns контрольного плейна Istio. ([Kiali][1])

* **Способ установки**
  При установке **без оператора** (ваш случай, ConfigMap) Kiali не умеет сам создавать Roles на каждый ns, поэтому практически обязателен режим `cluster_wide_access: true`. (Helm-серверный чарт тоже поддерживает только cluster-wide). ([Kiali][1])

* **Operator Namespace Watching / reconcile** (актуально, если когда-нибудь перейдёте на оператор)
  При `cluster_wide_access: false` новые ns станут видимы только после reconcile оператора (периодически/по событию). ([Kiali][1])

* **Мультикластер**
  Есть `deployment.discovery_selectors.overrides` — отдельные списки селекторов для удалённых кластеров; они полностью **заменяют** `default` для конкретного кластера. ([Kiali][1])

* **Per-user RBAC**
  Селекторы определяют «какие ns может видеть Kiali в принципе», но что увидит **конкретный пользователь**, дополнительно ограничивает кластерный RBAC (Roles/ClusterRoles + Bindings). ([Kiali][4])

* **Несколько Kiali с cluster-wide**
  Если поднимете несколько инстансов с `cluster_wide_access: true`, им нужны **уникальные** `deployment.instance_name`. ([Kiali][1])

---

## Готовые минимальные шаблоны

**A. Ручная установка (ConfigMap Kiali Server), “видны все ns” кроме системных**

```yaml
deployment:
  cluster_wide_access: true
# discovery_selectors: []  # не указываем
```

([Kiali][1])

**B. То же + включить выбранные системные ns**

```yaml
deployment:
  cluster_wide_access: true
  discovery_selectors:
    default:
      - matchLabels:
          kiali.io/visible: "true"  # поставьте эту метку на нужные системные ns
```

([Kiali][1])

---

### Короткая проверка вашего файла

1. Убедитесь, что **нет** `deployment.accessible_namespaces` и любых `api.namespaces.*`. ([Kiali][1])
2. Для ручной установки держите `deployment.cluster_wide_access: true`. ([Kiali][1])
3. Если хотите «все ns» — просто не задавайте discovery selectors; если нужны системные, добавьте label-селектор под них. ([Kiali][1])

Если покажете свой текущий `config.yaml`, быстро укажу конкретные строки, что удалить/заменить.

[1]: https://kiali.io/docs/configuration/namespace-management/ "Namespace Management | Kiali"
[2]: https://kiali.io/news/release-notes/ "Release Notes | Kiali"
[3]: https://raw.githubusercontent.com/istio/istio/release-1.25/samples/addons/kiali.yaml?utm_source=chatgpt.com "https://raw.githubusercontent.com/istio/istio/rele..."
[4]: https://kiali.io/docs/configuration/rbac/ "Namespace access control | Kiali"

---


Лöscha, вижу три вещи, которые сейчас мешают Kiali 2.15 «увидеть» ворклоады у тебя в установке через **ConfigMap** (без оператора).

# Что починить в твоём файле прямо сейчас

## 1) Пара меток приложения/версии

В конфиге задано только:

```yaml
istio_labels:
  version_label_name: app.kubernetes.io/version
```

Когда ты указываешь **хоть одно** поле из `istio_labels.*`, Kiali перестаёт «подбирать» разные схемы меток и ждёт **ровно пару** `app_label_name` + `version_label_name`.
Если на Pod’ах у тебя повсеместно `app.kubernetes.io/name`, а поля `app_label_name` нет, Kiali не сопоставит Pod’ы ↔ workloads — в UI будет пусто, а в логах сыпятся «…labels \[] not found».

**Исправление (вариант 1 — рекомендую):**

```yaml
istio_labels:
  app_label_name: app.kubernetes.io/name
  version_label_name: app.kubernetes.io/version
```

**Альтернатива (вариант 2):**
вообще **убери** блок `istio_labels:` — тогда Kiali снова будет автоматически распознавать стандартные пары (`canonical-*`, `app.kubernetes.io/*`, `app`/`version`). Но лучше зафиксировать конкретную пару, чтобы поведение было предсказуемым.

## 2) discovery\_selectors

У тебя стоит пустой объект:

```yaml
deployment:
  discovery_selectors: {}
```

Для установки **без оператора** он не даёт пользы и может путать: в server-конфиге это поле не нужно, а логика «селекторы заданы/не заданы» в 2.x влияет на то, какие неймспейсы Kiali сканирует.

**Исправление:**
просто **удали весь ключ** `discovery_selectors` (и весь блок `deployment:` тут не нужен — см. пункт 3).
При отсутствии селекторов и с правильными RBAC Kiali покажет **все** (кроме системных) неймспейсов.
Если захочешь включить системные — пометь их, например, `kiali.io/visible=true` и добавь селектор уже осознанно:

```yaml
deployment:
  discovery_selectors:
    default:
      - matchLabels:
          kiali.io/visible: "true"
```

(Но это нужно только при установке через оператор. В твоём сценарии — убрать.)

## 3) Половина полей — «операторные» и сервер их игнорирует

Ты кладёшь в ConfigMap **server-конфиг**, а в нём много полей, которые работают только при установке через **Kiali Operator/Helm**:
`deployment.*`, `ingress.*`, `image_*`, `resources`, `replicas`, `security_context`, `service_type`, `node_selector`, `tolerations`, `priority_class_name`, `namespace`, `instance_name`, `version_label`, `view_only_mode` и т.д.
Сервер эти ключи **не применяет**. Если опираться на них (например, на `cluster_wide_access: true`), можно создать ложное ощущение, что «доступ есть», хотя нужные **RBAC**-права надо выдавать отдельно (ClusterRole/Binding для serviceaccount Kiali).

**Что сделать:**

* Либо **очисти** ConfigMap от операторных ключей (оставь только то, что реально читает сервер: `server`, `auth`, `external_services`, `kubernetes_config`, `istio_labels`, `kiali_feature_flags`, `login_token`, `identity` и т.п.).
* Либо просто **знай**, что всё из `deployment.*`/`ingress.*` здесь «декорации» и не работают.

> Отдельно: `pod_labels: sidecar.istio.io/inject: "true"` — лучше убрать. Kiali обычно **не** запускают в mesh; сайдкар может мешать исходящему трафику на Kubernetes API и внешние сервисы (нужны ServiceEntry/права и пр.), что тоже приводит к пустым спискам.

# Мини-патч (суть)

```diff
- istio_labels:
-   version_label_name: app.kubernetes.io/version
+ istio_labels:
+   app_label_name: app.kubernetes.io/name
+   version_label_name: app.kubernetes.io/version

- deployment:
-   discovery_selectors: {}
+ # (удалить полностью весь ключ discovery_selectors; при желании — весь блок deployment: как неиспользуемый сервером)

- pod_labels:
-   sidecar.istio.io/inject: "true"
+ # (опционально удалить, чтобы не инжектить сайдкар в Kiali)
```

# Обязательные проверки (вне конфига)

1. **RBAC** (так как у тебя нет оператора, он их не создаёт):

```bash
# подставь свой namespace/SA Kiali
kubectl auth can-i --as=system:serviceaccount:kiali:kiali -A get pods
kubectl auth can-i --as=system:serviceaccount:kiali:kiali -A list deployments
kubectl auth can-i --as=system:serviceaccount:kiali:kiali -A watch namespaces
```

Все должны отвечать **yes**. Если нет — добавь кластерный read-only RBAC (ClusterRole/ClusterRoleBinding).

2. **Метки на Pod’ах** — хотя бы где-то в кластере проверь, что действительно есть пара:

```bash
kubectl get pods -A \
  -o custom-columns='NS:.metadata.namespace,POD:.metadata.name,APP:.metadata.labels.app\.kubernetes\.io/name,VER:.metadata.labels.app\.kubernetes\.io/version' \
  | head -30
```

Если `APP`/`VER` пустые — нужно добавить метки в манифесты.

---

Если после этого workloads всё ещё пустые — пришли, пожалуйста:

* вывод трёх `kubectl auth can-i …` из блока выше,
* 10–15 строк старта логов Kiali (там видно, какие label names он принял и какие кластерные селекторы применил).
  Добью до рабочей конфигурации.


---

Круто, спасибо за скрины. Ниже — «чистый» **config.yaml для Kiali 2.15**, который корректен при **развёртывании без оператора** (т.е. это именно серверный конфиг Kiali, а не CR оператора/Helm-values). Я сохранил твои реальные адреса Prometheus/Jaeger и статус-блок Istio, убрал все операторные ключи и зафиксировал пару меток `app.kubernetes.io/name` + `app.kubernetes.io/version`, чтобы Kiali точно собрал Workloads.

> ВАЖНО: этот файл сам по себе **не даёт прав**. Обязательно нужен ClusterRole/Binding для serviceaccount Kiali (кластерный read-only).

---

```yaml
# Kiali server config (standalone, no operator)
# Помести в ConfigMap как data.config.yaml и смонтируй в /opt/kiali/config/config.yaml

auth:
  strategy: anonymous
  # если будет OIDC — добавишь блок openid: {...}

logger:
  log_format: json
  log_level: info
  sampler_rate: "1"
  time_field_format: "2006-01-02T15:04:05Z07:00"

server:
  port: 20001
  web_root: /kiali
  observability:
    metrics:
      enabled: true
      port: 9090
    tracing:
      enabled: true
      collector_type: otel
      collector_url: simplest-collector.jaeger:4317
      otel:
        protocol: grpc
        tls_enabled: false

login_token:
  # Секрет для подписи login-токена Kiali (подставь свой)
  signing_key: "<REPLACE_WITH_RANDOM_32+_CHARS>"

# Если используешь мультикластерные remote-secrets — это как раз серверный блок
clustering:
  autodetect_secrets:
    enabled: true
    label: kiali.io/multiCluster=true

# Фиксируем СХЕМУ меток, чтобы Workloads точно собирались
istio_labels:
  app_label_name: app.kubernetes.io/name
  version_label_name: app.kubernetes.io/version

kiali_feature_flags:
  certificates_information_indicators:
    enabled: true
    secrets:
      - cacerts
      - istio-ca-secret
  disabled_features: []

ui_defaults:
  # Просто дефолтный выбор namespace в UI — опционально
  namespaces:
    - aces
    - asm-gateway
    - fx-client-admin
    - rms-forge
    - idc

validations:
  # Оставил твоё отключение правила
  ignore:
    - KIA1301

kubernetes_config:
  burst: 200
  qps: 175
  cache_enabled: true
  cache_duration: 300
  cache_expiration: 300
  cache_token_namespace_duration: 10
  excluded_workloads:
    - CronJob
    - Job
    - ReplicationController
  # ничего не исключаем на уровне ресурсов
  skip_clusters: []
  skipTLSVerify: false

external_services:
  istio:
    # Эти поля сервер читает; остальное (istiod_* и т.п.) авто-обнаружается
    istio_namespace: istio-system
    root_namespace: istio-system
    istio_injection_annotation: sidecar.istio.io/inject
    istio_sidecar_annotation: sidecar.istio.io/status
    istio_api_enabled: false
    envoy_admin_local_port: 15000
    component_status:
      components:
        - app_label: istiod
          is_core: true
          is_proxy: false
        - app_label: istio-ingressgateway
          namespace: asm-gateway
          is_core: true
          is_proxy: true
        - app_label: istio-eastwestgateway
          namespace: asm-gateway
          is_core: false
          is_proxy: true
  prometheus:
    url: "http://prometheus-platform.monitoring:9090"
  tracing:
    enabled: true
    # Для ссылок из UI (внешний адрес Jaeger)
    external_url: "https://jaeger.anthos-uk-wdc-01.dev.fichc.intranet.db.com"
    provider: jaeger
    use_grpc: true
    grpc_port: 16685
    # Внутренний адрес (как Kiali ходит в Jaeger Query)
    internal_url: "http://simplest-query.jaeger:16685"
  grafana:
    enabled: false
```

---

## Что именно я убрал и почему

* Весь блоки **`deployment.*`**, **`ingress.*`**, **`image_*`**, **`resources/replicas/security_context/node_selector/tolerations/priority_class_name`**, **`service_type`**, **`namespace/instance_name/version_label/view_only_mode`** — это **операторные/helm-ключи**, сервер их не применяет.
* **`discovery_selectors`** — не нужен в standalone-режиме. Видимость «всех NS» обеспечивается RBAC.
* **`pod_labels: sidecar.istio.io/inject: "true"`** — не инжектим сайдкар в Kiali (так безопаснее и проще).
* Лишние «global/commitSha/ticketId/istiohost/kiali\_extras…» — это не серверные ключи.

## Что важно проверить вне конфига

1. **RBAC** для serviceaccount Kiali (кластерный read-only), иначе Workloads будут пустыми:

```bash
# подставь свой ns и имя SA
kubectl auth can-i --as=system:serviceaccount:kiali:kiali -A get pods
kubectl auth can-i --as=system:serviceaccount:kiali:kiali -A list deployments
kubectl auth can-i --as=system:serviceaccount:kiali:kiali -A watch namespaces
```

Должно быть **yes** везде. Если нет — выдай ClusterRole/ClusterRoleBinding.

2. **Метки на Pod’ах** соответствуют выбранной паре:

```bash
kubectl get pods -A \
  -o custom-columns='NS:.metadata.namespace,POD:.metadata.name,APP:.metadata.labels.app\.kubernetes\.io/name,VER:.metadata.labels.app\.kubernetes\.io/version' \
  | head -30
```

Если `APP/VER` пустые — добавь метки в манифесты или смени пару в `istio_labels`.

---

Хочешь — сгенерирую сразу готовый `ConfigMap` и минимальный `ClusterRole/Binding` под этот конфиг.


---


Отличный вопрос. Нужно **узнать точные `namespace` и `serviceAccountName`**, с которыми реально стартует твой Kiali-pod, и использовать их в виде
`system:serviceaccount:<NAMESPACE>:<SA_NAME>` (плюс группы для корректной имперсонизации).

## 1) Найти namespace и ServiceAccount Kiali

Попробуй по «стандартным» лейблам; если не найдёт — поменяй селектор на `app=kiali`.

```bash
# где запущен Kiali и какой SA использует
kubectl get deploy -A -l app.kubernetes.io/name=kiali \
  -o custom-columns='NS:.metadata.namespace,DEPLOY:.metadata.name,SA:.spec.template.spec.serviceAccountName'

# если поле пустое → используется default SA соответствующего ns
# проверим pod на всякий случай:
kubectl get pod -A -l app.kubernetes.io/name=kiali \
  -o custom-columns='NS:.metadata.namespace,POD:.metadata.name,SA:.spec.serviceAccountName'
```

Если `SA` пустой → это означает `serviceAccountName: default`, т.е. идентификатор будет
`system:serviceaccount:<тот_же_namespace>:default`.

## 2) Сформировать строку для `--as`

Шаблон:

```
system:serviceaccount:<NAMESPACE>:<SA_NAME>
```

Примеры:

* `system:serviceaccount:kiali:kiali`
* `system:serviceaccount:istio-system:kiali`
* `system:serviceaccount:kiali:default` (если SA не задан в deployment)

## 3) ВАЖНО: добавить группы при имперсонизации

Чтобы эмуляция была точной (иначе иногда выходят «ложные NO»), добавь группы сервис-аккаунтов:

```
--as-group=system:serviceaccounts \
--as-group=system:serviceaccounts:<NAMESPACE> \
--as-group=system:authenticated
```

## 4) Проверки прав (кластерные и namespace-овые)

```bash
NS=<подставь из шага 1>
SA=<подставь из шага 1>
AS="--as=system:serviceaccount:${NS}:${SA} \
     --as-group=system:serviceaccounts \
     --as-group=system:serviceaccounts:${NS} \
     --as-group=system:authenticated"

# кластерные ресурсы / все неймспейсы
kubectl auth can-i ${AS} -A get pods
kubectl auth can-i ${AS} -A list deployments
kubectl auth can-i ${AS} -A watch namespaces
kubectl auth can-i ${AS} get nodes

# подробный список прав (в пределах одного ns)
kubectl auth can-i ${AS} --list -n default
```

Ожидаемо всё выше должно быть **yes**, иначе Kiali не увидит ворклоады во всех ns.

## 5) Где посмотреть, чем именно «скормлены» права SA

Быстро найти биндинги, которые цепляют этот SA:

```bash
# ClusterRoleBinding'и, где фигурирует наш SA
kubectl get clusterrolebinding -o json | \
  jq -r '.items[] | select(.subjects[]? | .kind=="ServiceAccount" and .name=="'"$SA"'" and .namespace=="'"$NS"'") | .metadata.name'

# Аналогично для RoleBinding (namespaced)
kubectl get rolebinding -A -o json | \
  jq -r '.items[] | select(.subjects[]? | .kind=="ServiceAccount" and .name=="'"$SA"'" and .namespace=="'"$NS"'") | [.metadata.namespace,.metadata.name] | @tsv'
```

(Если `jq` не под рукой — можно `kubectl get *binding -o yaml | grep` по имени SA/NS.)

---

Если хочешь, сгенерирую минимальные `ClusterRole`/`ClusterRoleBinding` под найденные `NS` и `SA`, чтобы точно дать Kiali read-only кластерные права.


