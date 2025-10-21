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

