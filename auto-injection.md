Ниже — 2 рабочих пути для Kiali 2.15 (установлен в namespace `kiali`), чтобы он **видел только те неймспейсы, где реально есть Istio-нагрузки**, и при этом **список обновлялся автоматически** при добавлении/удалении неймспейсов.

> С релиза **Kiali 2.0 старый параметр `deployment.accessible_namespaces` больше не поддерживается**. Вместо него используются **cluster-wide access** и **discovery selectors**. Если вы всё ещё ищете `accessible_namespaces: ["**"]` — это уже прошлое. ([kiali.io][1])

---

# Вариант A (проще): Helm chart **kiali/kiali-server**

(кластерные права + селекторы для видимости)

**Почему так:** server-chart **не создаёт namespace-scoped Roles** по селекторам, значит ему нужен **cluster-wide** доступ; селекторы ограничат **видимые** в UI namespaces (динамически). ([kiali.io][1])

1. `values.yaml` для `kiali/kiali-server` (установлен в `kiali`):

```yaml
deployment:
  namespace: kiali
  # Для server-chart желательно оставить cluster-wide включённым
  cluster_wide_access: true

  # Список discovery selectors определяет, какие NS будут ВИДНЫ в Kiali
  # Покроем оба типовых случая автоинъекции: "classic" и "revisioned".
  discovery_selectors:
    default:
      - matchLabels:
          istio-injection: "enabled"     # classic auto-injection
      - matchExpressions:                # revision-based auto-injection
        - key: istio.io/rev
          operator: Exists
      # Если используете Ambient, раскомментируйте:
      # - matchLabels:
      #     istio.io/dataplane-mode: ambient
```

2. Установка/обновление:

```bash
helm repo add kiali https://kiali.org/helm-charts
helm upgrade -n kiali --install kiali-server kiali/kiali-server -f values.yaml
```

3. Динамика:
   Когда вы **помечаете** новый namespace под Istio (например, `istio-injection=enabled` или добавляете `istio.io/rev=1-22`), он **автоматически появится** в списке namespaces Kiali (за счёт селекторов и watch’ей). Системные `kube-*` и т.п. не будут показываться, если селекторы пустые; при явных селекторах вы и так показываете только «свои» NS. ([kiali.io][1])

> Примечание: Kiali **не читает селекторы из Istio MeshConfig** — задайте в Kiali **те же селекторы**, что и в Istio, вручную (как выше). ([kiali.io][1])

---

# Вариант B (жёстче по безопасности): Helm chart **kiali-operator** + Kiali CR

(пер-namespace Roles, автоподхват новых NS через reconcile)

**Почему так:** оператор умеет, при `cluster_wide_access: false`, **создавать Roles** только в тех неймспейсах, которые совпали по селекторам. Это уменьшает права Kiali до нужного минимума. ([kiali.io][1])

1. Устанавливаем оператор (важно: дать ему право создавать ClusterRoles при необходимости):

```bash
helm upgrade -n kiali-operator --create-namespace --install kiali-operator kiali/kiali-operator \
  --set clusterRoleCreator=true
```

2. Создаём CR `Kiali` в `kiali`:

```yaml
# kiali-cr.yaml
apiVersion: kiali.io/v1alpha1
kind: Kiali
metadata:
  name: kiali
  namespace: kiali
  annotations:
    # Чтобы оператор периодически пересматривал список NS (автоподхват новых):
    ansible.sdk.operatorframework.io/reconcile-period: 60s
spec:
  deployment:
    cluster_wide_access: false     # безопасность: без глобальных прав
    discovery_selectors:
      default:
        - matchLabels:
            istio-injection: "enabled"
        - matchExpressions:
          - key: istio.io/rev
            operator: Exists
        # - matchLabels: { istio.io/dataplane-mode: ambient }  # если нужно
```

```bash
kubectl apply -f kiali-cr.yaml
```

3. Динамика:
   Оператор будет **переустанавливать роли** по CR (каждые 60 секунд по аннотации выше, либо при любых изменениях CR/аннотаций/создании NS), подхватывая **новые/удалённые** соответствующие неймспейсы. ([kiali.io][1])

> Важно: если Istio control plane находится НЕ в `kiali`, его namespace тоже должен совпасть по вашим селекторам, иначе дайте ему дополнительную метку и включите её в селекторы (Kiali должен иметь доступ к control plane). ([kiali.io][1])

---

## Часто нужные команды

Пометить namespace под классическую автоинъекцию:

```bash
kubectl label ns my-app istio-injection=enabled --overwrite
```

Пометить namespace под ревизию:

```bash
kubectl label ns my-app istio.io/rev=1-22 --overwrite
```

Принудительно «ткнуть» оператор на reconcile (если не хотите ждать период):

```bash
kubectl annotate kiali kiali -n kiali --overwrite trigger-reconcile="$(date)"
```

([kiali.io][1])

---

## Краткое резюме выбора

* **Нужен минимум телодвижений** → **Вариант A (server-chart + cluster-wide + discovery selectors)**.
* **Нужны минимальные права (RBAC по NS)** → **Вариант B (operator + CR + discovery selectors + reconcile)**.

Обе схемы **автоматически** подхватывают новые неймспейсы за счёт селекторов (и reconciliation в варианте с оператором). Подробности — в актуальной документации по управлению неймспейсами в Kiali 2.x. ([kiali.io][1])

Если хочешь, могу сгенерировать готовые манифесты под твою сетку ревизий (`istio.io/rev`), control plane и изоляцию служебных NS.

[1]: https://kiali.io/docs/configuration/namespace-management/ "Namespace Management | Kiali"


---
---
---

Да. Я перепроверил по актуальным докам Kiali (обновлены 12 сен 2025) — всё, что я написал, соответствует реальности:

* Начиная с **Kiali 2.0** параметры вроде `deployment.accessible_namespaces` и `api.namespaces.*` **удалены**. Вместо них используются **`deployment.cluster_wide_access`** и **`deployment.discovery_selectors`**. ([kiali.io][1])
* **Server Helm Chart** не создаёт per-namespace `Role/RoleBinding` по селекторам — значит для него нужен **`cluster_wide_access: true`**; при этом **`discovery_selectors`** ограничивают **видимые** в UI неймспейсы (динамически). ([kiali.io][1])
* **Kiali Operator** при `cluster_wide_access: false` по `spec.deployment.discovery_selectors.default` находит подходящие NS и **создаёт Roles** в них (минимальные права). Для автоподхвата новых NS можно задать аннотацию **`ansible.sdk.operatorframework.io/reconcile-period: 60s`** или «триггерить» reconcile аннотацией. ([kiali.io][1])
* **Важно:** Kiali **не читает** Istio MeshConfig discoverySelectors — указывайте те же селекторы **в Kiali** отдельно. Также убедитесь, что в селекторах есть **namespace(ы) control plane** Istio. ([kiali.io][1])
* Метки для автоматической инъекции в NS — это стандартные `istio-injection=enabled` (classic) и/или `istio.io/rev=<revision>` (revision-based). ([Istio][2])

Если нужно, сгенерирую тебе готовые `values.yaml` (server chart) или `Kiali` CR (operator) под твою схему меток и ревизий.

[1]: https://kiali.io/docs/configuration/namespace-management/ "Namespace Management | Kiali"
[2]: https://istio.io/latest/docs/setup/additional-setup/sidecar-injection/?utm_source=chatgpt.com "Installing the Sidecar"

---
---
---


Коротко: **нет, одного `cluster_wide_access: true` в ConfigMap недостаточно, чтобы «само починилось»**, если в кластере сломаны/неверные RBAC-биндинги.
Для standalone Helm-установки (`kiali/kiali-server`) нужно одновременно:

1. **Корректные кластерные роли/биндинги** для SA Kiali.
2. (Опционально для авто-фильтрации) **`deployment.discovery_selectors`** — чтобы Kiali показывал только те NS, где есть Istio.
3. **Control plane NS должен попадать под ваши селекторы** (в Kiali v2 это новое требование). ([kiali.io][1])

---

# Что именно должно быть в кластере (standalone Helm, без оператора)

При установке из **`kiali/kiali-server`** чарт **создаёт** (по умолчанию):

* `ServiceAccount`: `kiali` в вашем ns (например, `kiali`).
* `ClusterRole`: `kiali` (широкий read, плюс операции на Istio-ресурсах, port-forward, pods/log и т.п.).
* `ClusterRoleBinding`: `kiali` → субъект **`system:serviceaccount:kiali:kiali`**.
* `Role` в ns control plane (обычно `istio-system`) для доступа к секретам (CA),
* `RoleBinding` в ns control plane, который биндит **SA из ns Kiali** к этой Role.
  Это видно как в шаблонах server-чарта/исторических манифестах, так и по поведению чарта (в т.ч. режим `view_only_mode` биндит viewer-роль через Helm). ([GitHub][2])

> Важно: **Server-chart не создаёт per-namespace Roles по селекторам** — он полагается на **cluster-wide** доступ, а селекторы лишь **ограничивают, что видно в UI**. Для per-NS RBAC нужны были бы возможности оператора (у вас он принципиально не используется). ([kiali.io][3])

---

# Проверка и типовые «поломки» RBAC

1. **Правильный subject в ClusterRoleBinding**
   Частая ошибка — биндят на SA **в неверном namespace** (например, `istio-system` вместо `kiali`).

```bash
kubectl get clusterrolebinding kiali -o yaml | grep -A5 subjects:
# Должно быть:
# kind: ServiceAccount
# name: kiali
# namespace: kiali   # <-- ваш ns установки Kiali
```

2. **RoleBinding в ns control plane** (доступ к секретам и т.п.)

```bash
kubectl get rolebinding -n istio-system kiali-controlplane -o yaml | grep -A6 subjects:
# namespace в subject тоже должен быть "kiali"
```

3. **Убедиться, что Deployment реально использует нужный SA**

```bash
kubectl get deploy -n kiali kiali -o jsonpath='{.spec.template.spec.serviceAccountName}{"\n"}'
# Ожидаем: kiali
```

4. **Проверить ключевые разрешения от имени SA**

```bash
# SA Kiali должен уметь читать список NS, иначе селекторы не сработают вообще
kubectl auth can-i --as=system:serviceaccount:kiali:kiali list namespaces

# Чтение Istio CRDs
kubectl auth can-i --as=system:serviceaccount:kiali:kiali list virtualservices.networking.istio.io -A
kubectl auth can-i --as=system:serviceaccount:kiali:kiali list destinationrules.networking.istio.io -A

# (Если используете Gateway API)
kubectl auth can-i --as=system:serviceaccount:kiali:kiali list gateways.gateway.networking.k8s.io -A
```

> Если `can-i list namespaces` возвращает `no` — Kiali **не сможет** обработать discovery-selectors. ([GitHub][4])

---

# Настройки Helm/ConfigMap, которые должны быть

## 1) RBAC на уровне чарта (обычно по умолчанию уже есть)

Ничего «в Deployment» менять не нужно — права задаёт **RBAC** (ClusterRole/Binding), а не сам pod. Но проверьте, что вы **не** включали что-то, что урезает RBAC, например только viewer-доступ, если вам нужны правки из UI.

```yaml
# values.yaml (фрагмент)
deployment:
  cluster_wide_access: true        # необходимо для server-чарта
  # Если хотите read-only:
  # view_only_mode: true
```

Смысл `cluster_wide_access: true`: чарту «можно» создать ClusterRole/ClusterRoleBinding. Это даёт Kiali **доступ**, а не «фильтр видимости». Фильтрацию даёт следующий пункт. ([kiali.io][5])

## 2) Авто-фильтрация видимых NS (динамически) через discovery selectors

Чтобы Kiali **показывал только те NS, где действительно есть Istio-нагрузки** — добавьте селекторы. И **обязательно включите ns control plane** в эти селекторы (или промаркируйте его отдельно).

```yaml
# values.yaml (фрагмент)
deployment:
  cluster_wide_access: true
  discovery_selectors:
    default:
      # classic auto-injection
      - matchLabels:
          istio-injection: "enabled"
      # revision-based auto-injection
      - matchExpressions:
        - key: istio.io/rev
          operator: Exists
      # Явно включим control plane namespace через отдельную метку:
      - matchLabels:
          kiali-access: "controlplane"
```

И промаркируйте control plane ns (если он не совпадает с двумя правилами выше):

```bash
kubectl label ns istio-system kiali-access=controlplane --overwrite
```

* В Kiali v2 **поддержка старых полей** типа `accessible_namespaces` удалена — нужны **discovery selectors**. ([v2-0.kiali.io][6])
* **Control plane ns обязан попадать в селекторы** (требование новых версий/релиз-ноты). ([kiali.io][7])

> После изменения ConfigMap/values не забудьте перезапустить pod Kiali:

```bash
kubectl rollout restart deploy -n kiali kiali
```

---

# Ответы на ваши вопросы «да/нет»

* **«Этого достаточно — `cluster_wide_access: true`?»**
  Нет, это **не чинит** возможные ошибки RBAC и **не ограничивает видимость**. Это лишь разрешает чарту создать кластерные права. Если RBAC/биндинги неверные — нужно их поправить. Если нужна динамическая фильтрация — добавьте `discovery_selectors`. ([kiali.io][5])

* **«Должно ли что-то меняться в самом Deployment?»**
  Нет. Деплоймент должен просто ссылаться на корректный `serviceAccountName`. Все «права» живут в ClusterRole/Role(Binding). См. проверки выше.

* **«В Helm-чарте есть всё необходимое по кластерным ролям?»**
  Да, официальный **`kiali/kiali-server`** ставит SA, ClusterRole, ClusterRoleBinding и нужные роли/биндинги в control plane NS. Если их нет/они указывают на неверный namespace — это симптом локальной модификации/ручного редактирования или неприменённых шаблонов. ([GitHub][2])

---

# Быстрый чек-лист исправления

1. Исправьте/создайте правильные биндинги:

   * `ClusterRoleBinding kiali` → `system:serviceaccount:kiali:kiali`.
   * `RoleBinding kiali-controlplane` в ns control plane → тот же субъект.
2. Убедитесь, что `Deployment kiali` использует SA `kiali`.
3. Включите селекторы (`deployment.discovery_selectors`) + включите ns control plane (через метку или отдельное правило).
4. `rollout restart` Kiali.
5. Повторите `kubectl auth can-i …` для ключевых API (namespaces, istio CRDs, gateway API при необходимости).

Если пришлёшь `kubectl get clusterrolebinding kiali -o yaml` и `… rolebinding -n istio-system kiali-controlplane -o yaml`, я укажу, что именно нужно поправить в твоём кластере.

[1]: https://kiali.io/docs/configuration/rbac/?utm_source=chatgpt.com "Namespace access control"
[2]: https://raw.githubusercontent.com/istio/istio/release-1.15/samples/addons/kiali.yaml?utm_source=chatgpt.com "https://raw.githubusercontent.com/istio/istio/rele..."
[3]: https://kiali.io/docs/configuration/namespace-management/?utm_source=chatgpt.com "Namespace Management"
[4]: https://github.com/kiali/kiali/issues/7546?utm_source=chatgpt.com "Enhance namespace accessibility based on ..."
[5]: https://kiali.io/docs/faq/general/?utm_source=chatgpt.com "General"
[6]: https://v2-0.kiali.io/news/release-notes/?utm_source=chatgpt.com "Release Notes"
[7]: https://kiali.io/news/release-notes/?utm_source=chatgpt.com "Release Notes"

---
---
---


Коротко: **RoleBinding `kiali-controlplane` в `istio-system` должен был создать сам Helm-чарт `kiali/kiali-server` при `helm install/upgrade`.** Он идёт вместе с `Role kiali-controlplane` в `istio-system` и биндит **ServiceAccount `kiali` из namespace установки Kiali** к этой роли. Если его нет — либо чарт ставили/обновляли с ограничениями по RBAC, либо релиз/NS меняли и биндинг «потерялся», либо используется не тот чарт/значения. ([GitHub][1])

### Когда и кем добавляется этот RoleBinding

* **Кем:** Helm-релиз `kiali-server` (официальный server-чарт Kiali).
* **Когда:** во время `helm install`/`helm upgrade` Kiali. В шаблонах чарта есть:

  * `ClusterRole kiali` + `ClusterRoleBinding kiali` (кластерные права для SA Kiali),
  * **`Role kiali-controlplane` в `istio-system`** (доступ к секретам control plane),
  * **`RoleBinding kiali-controlplane` в `istio-system`**, subject → `system:serviceaccount:<NS_KIALI>:kiali`. ([GitHub][1])

> Примечание: для server-чарта **cluster-wide режим обязателен** (`deployment.cluster_wide_access=true`) — он даёт права; а **что видно в UI** лучше ограничивать `deployment.discovery_selectors`. Но **сам по себе** флаг `cluster_wide_access=true` не «чинит» отсутствующие RBAC-ресурсы. ([kiali.io][2])

---

## Что проверить прямо сейчас

1. **Есть ли ресурс в самом релизе Helm**

```bash
helm get manifest -n kiali kiali-server | grep -n "kiali-controlplane" -A4 -B4
```

Если ничего не найдено — ваш релиз (или форк чарта) **не создаёт** этот биндинг.

2. **Правильный subject у биндинга**

```bash
kubectl get clusterrolebinding kiali -o yaml | grep -A5 subjects:
# Ожидаем: kind: ServiceAccount / name: kiali / namespace: kiali
```

3. **SA в деплойменте**

```bash
kubectl get deploy -n kiali kiali -o jsonpath='{.spec.template.spec.serviceAccountName}{"\n"}'
# Должно быть: kiali
```

4. **Права SA на ключевые ресурсы**

```bash
kubectl auth can-i --as=system:serviceaccount:kiali:kiali list namespaces
kubectl auth can-i --as=system:serviceaccount:kiali:kiali list virtualservices.networking.istio.io -A
```

Если `list namespaces = no`, селекторы видимости **не будут работать**. ([kiali.io][3])

---

## Почему биндинга может не быть

* Установили `kiali-server` **раньше** в другом NS (например, `istio-system`), потом переместили Kiali в `kiali`, а RoleBinding остался с subject на старый NS.
* **Helm не имел прав** создавать Role/RoleBinding в `istio-system` → ресурс не создался (проверьте события/логи установки).
* Используется **обёртка/дистрибутив** (Rancher/BB/свой чарт), где RBAC изменён.
* Чарт/values модифицированы (некоторые обёртки позволяют **выключать** создание RBAC).

---

## Как починить

### Вариант 1 — «правильно» через Helm (рекомендую)

Сделайте `helm upgrade` тем же чартом/версией, убедившись, что:

* релиз в NS `kiali`;
* `deployment.cluster_wide_access=true` (для server-чарта это требование);
* корректно задан **control plane NS** (в современных релизах Kiali больше не читает старые поля `istio_namespace`, но RBAC к control plane чарт всё равно рендерит; а в **discovery selectors** нужно включить NS control plane, иначе он не будет виден в UI). ([kiali.io][4])

Проверить итоговые манифесты перед применением:

```bash
helm template -n kiali kiali-server kiali/kiali-server \
  --set deployment.cluster_wide_access=true \
  | grep -n "RoleBinding" -A6 -B6
```

### Вариант 2 — быстро создать вручную (если helm сейчас не трогаем)

> Подставьте ваш namespace установки Kiali в `subjects.namespace` (ниже — `kiali`).
> Если `Role kiali-controlplane` тоже отсутствует — примените оба манифеста.

```yaml
# Role в istio-system (минимум как в чартовых шаблонах)
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: kiali-controlplane
  namespace: istio-system
rules:
  - apiGroups: [""]
    resourceNames:
      - cacerts
      - istio-ca-secret
    resources:
      - secrets
    verbs: ["get","list","watch"]
---
# RoleBinding в istio-system к SA из ns kiali
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: kiali-controlplane
  namespace: istio-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: kiali-controlplane
subjects:
  - kind: ServiceAccount
    name: kiali
    namespace: kiali
```

Это соответствует историческим шаблонам `kiali-server` (имена те же). ([GitHub][1])

---

## Итог

* **Да,** нужный RoleBinding **должен был приехать из Helm-чарта** при установке/обновлении.
* Если его нет — чините через `helm upgrade` (предпочтительно) или создайте Role/RoleBinding вручную, как выше.
* И не забудьте: чтобы Kiali **видел только mesh-NS**, добавьте `deployment.discovery_selectors` и **включите в них control plane NS**, иначе он может быть скрыт в UI. ([kiali.io][5])

Если пришлёшь вывод `helm get values -n kiali kiali-server` и `helm get manifest…`, быстро укажу точную причину, почему биндинг не создался в твоём релизе.

[1]: https://raw.githubusercontent.com/istio/istio/release-1.18/samples/addons/kiali.yaml?utm_source=chatgpt.com "https://raw.githubusercontent.com/istio/istio/rele..."
[2]: https://kiali.io/docs/faq/installation/?utm_source=chatgpt.com "Installation"
[3]: https://kiali.io/docs/configuration/rbac/?utm_source=chatgpt.com "Namespace access control"
[4]: https://kiali.io/news/release-notes/?utm_source=chatgpt.com "Release Notes"
[5]: https://kiali.io/docs/configuration/namespace-management/?utm_source=chatgpt.com "Namespace Management"


---
---
---


Отлично, собрал для тебя «боевой набор» проверок — от самых быстрых до глубоких (PromQL, события, HPA, квоты, throttling). Всё copy-paste.

# 1) Быстрые sanity-чек-листы (kubectl)

**Состояние пода, рестарты, OOM:**

```bash
kubectl -n kiali get pods -o wide
kubectl -n kiali describe pod -l app=kiali | sed -n '1,200p'   # Events, OOMKilled, Liveness/Readiness
kubectl -n kiali get events --sort-by=.lastTimestamp | tail -n 50
```

**Фактическое потребление (нужен metrics-server):**

```bash
kubectl -n kiali top pod -l app=kiali
kubectl -n kiali top pod -l app=kiali --containers   # если несколько контейнеров
```

**Проверка RBAC/квот/лимитов в неймспейсе:**

```bash
kubectl -n kiali get resourcequota -o wide
kubectl -n kiali describe resourcequota
kubectl -n kiali get limitrange -o yaml
```

**Проверка HPA (если включён):**

```bash
kubectl -n kiali get hpa
kubectl -n kiali describe hpa kiali
```

**Убедиться, что деплойменти/реплики не зажаты квотами/лимитами:**

```bash
kubectl -n kiali describe deploy kiali | sed -n '1,200p'
kubectl -n kiali get rs -l app=kiali
```

---

# 2) Бенчмарк-критерии «всё ок»

Обычно «здоровый» профиль такой:

* **CPU**: p95 < **70% от лимита**, throttling < **10%**.
* **RAM**: Working Set < **80% от лимита**, **0** OOMKilled.
* **HPA**: не «упирается» постоянно в maxReplicas; масштабируется вверх/вниз.
* **Квоты**: используемые requests/limits < **85%** квот.

---

# 3) PromQL — текущая утилизация CPU/RAM vs лимиты

> Подставь `namespace="kiali"` и `pod=~"kiali-.*"` (или свой label-selector). Метрики от **kube-state-metrics** и **cAdvisor**/**kubelet**.

**CPU usage (в ядрах) по pod (p5m):**

```promql
sum by (pod) (
  rate(container_cpu_usage_seconds_total{namespace="kiali", pod=~"kiali-.*", image!=""}[5m])
)
```

**CPU limit по pod (ядра):**

```promql
sum by (pod) (
  kube_pod_container_resource_limits{namespace="kiali", pod=~"kiali-.*", resource="cpu"}
)
```

**CPU usage / limit (доля):**

```promql
sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="kiali", pod=~"kiali-.*", image!=""}[5m]))
/
sum by (pod) (kube_pod_container_resource_limits{namespace="kiali", pod=~"kiali-.*", resource="cpu"})
```

**Memory working set (байты) по pod:**

```promql
sum by (pod) (container_memory_working_set_bytes{namespace="kiali", pod=~"kiali-.*", image!=""})
```

**Memory limit (байты) по pod:**

```promql
sum by (pod) (kube_pod_container_resource_limits{namespace="kiali", pod=~"kiali-.*", resource="memory"})
```

**Memory usage / limit (доля):**

```promql
sum by (pod) (container_memory_working_set_bytes{namespace="kiali", pod=~"kiali-.*", image!=""})
/
sum by (pod) (kube_pod_container_resource_limits{namespace="kiali", pod=~"kiali-.*", resource="memory"})
```

---

# 4) Поиск OOM и «горячих» рестартов

**Количество рестартов контейнеров за последние 6 часов:**

```promql
sum by (pod) (
  increase(kube_pod_container_status_restarts_total{namespace="kiali", pod=~"kiali-.*"}[6h])
)
```

**Последняя причина завершения контейнера (OOMKilled):**

```promql
max by (pod, container) (
  kube_pod_container_status_last_terminated_reason{namespace="kiali", pod=~"kiali-.*"} == "OOMKilled"
)
```

---

# 5) CPU throttling (CFS) — детектор упора в лимит

> В разных сборках возможны метрики `container_cpu_cfs_throttled_seconds_total` и `container_cpu_cfs_periods_total`. Если второй нет, смотри **ratio по throttled_seconds / usage_seconds** как эвристику.

**Доля «задушенных» периодов (если есть *_periods_total):**

```promql
sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{namespace="kiali", pod=~"kiali-.*"}[5m]))
/
sum by (pod) (rate(container_cpu_cfs_periods_total{namespace="kiali", pod=~"kiali-.*"}[5m]))
```

**Эвристика throttling (если *_periods_total недоступны):**

```promql
sum by (pod) (rate(container_cpu_cfs_throttled_seconds_total{namespace="kiali", pod=~"kiali-.*"}[5m]))
/
sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="kiali", pod=~"kiali-.*", image!=""}[5m]) + 1e-9)
```

> **Порог:** устойчиво >0.1 (10%) — признак, что **лимит CPU слишком низкий** для нагрузки Kiali.

---

# 6) Запас по requests (на предмет preemption/долгой инициализации)

**Сумма requests vs limits по namespace:**

```promql
sum(kube_pod_container_resource_requests{namespace="kiali", resource="cpu"})
sum(kube_pod_container_resource_limits{namespace="kiali", resource="cpu"})
sum(kube_pod_container_resource_requests{namespace="kiali", resource="memory"})
sum(kube_pod_container_resource_limits{namespace="kiali", resource="memory"})
```

**Сколько реально используется в сравнении с requests (CPU):**

```promql
sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="kiali", pod=~"kiali-.*", image!=""}[5m]))
/
sum by (pod) (kube_pod_container_resource_requests{namespace="kiali", pod=~"kiali-.*", resource="cpu"})
```

> Если стабильно >> 1.0 — requests занижены (риск throttling/подвисаний при упоре ноды).

---

# 7) Проверки квот (ResourceQuota) — хватает ли места для HPA/скейлинга

**Использование/лимиты квот (CPU, memory, pods) по namespace:**

```promql
# hard
sum by (resource) (kube_resourcequota{namespace="kiali", type="hard"})
# used
sum by (resource) (kube_resourcequota{namespace="kiali", type="used"})
```

**Сумма лимитов контейнеров против квоты limits.cpu:**

```promql
sum(kube_pod_container_resource_limits{namespace="kiali", resource="cpu"})
/
sum(kube_resourcequota{namespace="kiali", resource="limits.cpu", type="hard"})
```

**Количество pod против квоты pods:**

```promql
count(kube_pod_info{namespace="kiali"}) 
/
sum(kube_resourcequota{namespace="kiali", resource="pods", type="hard"})
```

> Если **used/hard > 0.85**, квоту расширить, иначе HPA не поднимет реплики.

---

# 8) HPA — реально ли масштабируется

**Текущее состояние HPA:**

```promql
kube_horizontalpodautoscaler_status_current_replicas{namespace="kiali", horizontalpodautoscaler="kiali"}
kube_horizontalpodautoscaler_status_desired_replicas{namespace="kiali", horizontalpodautoscaler="kiali"}
```

**Упирается ли HPA в максимум:**

```promql
max_over_time(
  (kube_horizontalpodautoscaler_status_desired_replicas{namespace="kiali", horizontalpodautoscaler="kiali"}
   >= kube_horizontalpodautoscaler_spec_max_replicas{namespace="kiali", horizontalpodautoscaler="kiali"})[1h]
)
```

> Возвращает 1, если за последний час желаемые реплики = maxReplicas (нужно поднять maxReplicas/лимиты/квоты).

---

# 9) Backend-зависимости Kiali (Prometheus/Tracing) — не «тянут» ли вниз

**Латентность Prometheus query_range (p95):**

```promql
histogram_quantile(0.95,
  sum by (le) (
    rate(prometheus_http_request_duration_seconds_bucket{handler="/api/v1/query_range"}[5m])
  )
)
```

> Если пикает в секунды/десятки секунд — Kiali «тормозит» не из-за своих ресурсов, а из-за Prometheus.

**Ошибки HTTP 5xx у Prometheus API:**

```promql
sum(rate(prometheus_http_requests_total{code=~"5.."}[5m]))
```

---

# 10) Признаки «узких мест» в логах Kiali

```bash
kubectl -n kiali logs deploy/kiali --tail=500 | egrep -i \
"(throttl|rate limit|oom|alloc|out of memory|deadline|timeout|too many open files|429|5..)"
```

* `throttl` — часто намёк на CFS throttling или server-side rate-limit k8s API.
* `timeout/deadline exceeded` — медленный Prometheus/Jaeger/k8s API.

---

# 11) Точечные действия, если что-то «краснеет»

* **CPU usage/Throttling высокие:**
  Поднять `limits.cpu` (и, при необходимости, `requests.cpu`) на 25–50%; для пиков — увеличить `maxReplicas` HPA.

* **Memory usage/limit >80% или OOMKilled:**
  Поднять `limits.memory` на 30–50% (Kiali строит большие графы → всплески RAM). Параллельно сократить «тяжесть» графа (меньше NS/интервал, убрать «security/response time» метрики по умолчанию).

* **HPA упёрся в maxReplicas:**
  Увеличить `maxReplicas` + проверить квоты (`limits.cpu/memory`, `pods`).

* **Quotas близко к hard:**
  Расширить ResourceQuota или переместить Kiali в отдельный ns без жёстких квот.

* **Медленный Prometheus:**
  Урезать период графа по умолчанию, включить downsampling/recording rules, оптимизировать retention и ресурсы Prometheus.

---

# 12) Мини-алерты (PrometheusRule) на базовые симптомы

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: kiali-health
  namespace: monitoring
spec:
  groups:
  - name: kiali
    rules:
    - alert: KialiCpuThrottlingHigh
      expr: |
        (
          sum(rate(container_cpu_cfs_throttled_seconds_total{namespace="kiali", pod=~"kiali-.*"}[5m]))
          /
          sum(rate(container_cpu_usage_seconds_total{namespace="kiali", pod=~"kiali-.*", image!=""}[5m]) + 1e-9)
        ) > 0.1
      for: 10m
      labels: {severity: warning}
      annotations:
        summary: "Kiali CPU throttling >10%"

    - alert: KialiMemoryNearLimit
      expr: |
        (
          sum(container_memory_working_set_bytes{namespace="kiali", pod=~"kiali-.*", image!=""})
          /
          sum(kube_pod_container_resource_limits{namespace="kiali", pod=~"kiali-.*", resource="memory"})
        ) > 0.8
      for: 10m
      labels: {severity: warning}
      annotations:
        summary: "Kiali memory >80% of limit"

    - alert: KialiOOMKilled
      expr: |
        increase(kube_pod_container_status_restarts_total{namespace="kiali", pod=~"kiali-.*"}[30m]) > 0
      for: 1m
      labels: {severity: critical}
      annotations:
        summary: "Kiali restarted (possible OOM)"

    - alert: KialiHpaAtMax
      expr: |
        max_over_time(
          (kube_horizontalpodautoscaler_status_desired_replicas{namespace="kiali", horizontalpodautoscaler="kiali"}
          >= kube_horizontalpodautoscaler_spec_max_replicas{namespace="kiali", horizontalpodautoscaler="kiali"})[15m]
        ) == 1
      for: 15m
      labels: {severity: warning}
      annotations:
        summary: "Kiali HPA at maxReplicas ≥15m"
```

---

# 13) Что потестировать руками (нагрузочный сценарий для Kiali)

1. В UI построй **Graph** на **все видимые NS** (через discovery selectors) за **30–60 мин**.
2. Открой **Workloads** с валидациями и фильтрами метрик.
3. Запусти параллельно PromQL из секций 3–5 и смотри пики по RAM/CPU/throttling.

Если хочешь, скидывай вывод нескольких команд (`kubectl top`, `describe hpa`, результаты PromQL) — подберём точные `requests/limits`, `HPA` и квоты под твой профиль.

---
---
---

