Ок, сделаем это чисто и безопасно: покажу, как найти действующие Gatekeeper-констрейнты, а затем дам готовый **Constraint** (по шаблону `K8sProhibitRoleWildcardAccess`) с исключениями именно для ролей Kiali 2.15 (те, что генерит Helm-чарт: `<fullname>` и `<fullname>-viewer`). Плюс — вариант **patch** существующего констрейнта.

---

# Как найти существующие Constraints

```bash
# 1) Посмотреть, какие типы констрейнтов вообще есть
kubectl api-resources --api-group=constraints.gatekeeper.sh

# 2) Найти именно "запрет wildcard у ролей"
kubectl get k8sprohibitrolewildcardaccess.constraints.gatekeeper.sh -A

# 3) Если нашли — показать YAML
kubectl get k8sprohibitrolewildcardaccess.constraints.gatekeeper.sh <NAME> -n <NS> -o yaml

# 4) Убедиться, что работает аудит (смотрим, есть ли нарушения)
kubectl get k8sprohibitrolewildcardaccess.constraints.gatekeeper.sh <NAME> -o jsonpath='{.status.totalViolations}{"\n"}'
kubectl get k8sprohibitrolewildcardaccess.constraints.gatekeeper.sh <NAME> -o jsonpath='{.status.violations}{"\n"}' | head -c 2000; echo
```

Если список пуст — в кластере пока **нет** такого констрейнта (только шаблон/ConstraintTemplate). Тогда создадим свой.

---

# Вариант 1. Создать **новый** Constraint с исключением под Kiali

> Подходит, когда такого констрейнта ещё нет, либо вы хотите иметь **свою** версию отдельно (рекомендую хранить это в Git и применять через ArgoCD).

**Файл:** `constraints/prohibit-role-wildcard-access-kiali.yaml`

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sProhibitRoleWildcardAccess
metadata:
  name: prohibit-role-wildcard-access
spec:
  enforcementAction: deny   # можно временно поставить dryrun для «мягкой» проверки
  match:
    # Проверяем и ClusterRole, и Role во всех неймспейсах/кластерно:
    kinds:
      - apiGroups: ["rbac.authorization.k8s.io"]
        kinds: ["ClusterRole","Role"]
    # При желании можно исключить системные неймспейсы:
    # excludedNamespaces: ["kube-system","gatekeeper-system"]
  parameters:
    exemptions:
      clusterRoles:
        # Исключаем роли Kiali, генерируемые Helm-чартом:
        # 1) Точный список (если имя релиза фиксировано и известно):
        - name: "^<YOUR_KIALI_FULLNAME>$"             # напр. "^kiali$" или "^kiali-prod$"
          regexMatch: true
        - name: "^<YOUR_KIALI_FULLNAME>-viewer$"      # напр. "^kiali-viewer$"
          regexMatch: true

        # 2) Или универсальная маска, если встречаются канарейки/суффиксы:
        #   kiali, kiali-viewer, kiali-canary, kiali-viewer-canary, и т.п.
        # - name: "^kiali(-viewer)?(-[a-z0-9-]+)?$"
        #   regexMatch: true

      roles:
        # Обычно не нужно (Kiali создаёт кластерные роли). Оставьте пустым.
        # Пример на случай, если у вас есть namespaced Role с wildcard:
        # - name: "kiali"
        #   namespace: "kiali"
```

**Применение / порядок синка:**

* Сначала убедитесь, что `ConstraintTemplate` уже установлен (в Anthos/Policy Controller он есть по умолчанию).
* Примените этот файл **до** деплоя Kiali (или одновременно, но до создания его ролей):

  * В ArgoCD — дайте этому файлу sync-wave `-1`, а приложению Kiali — `0`.

Проверка:

```bash
kubectl get k8sprohibitrolewildcardaccess.constraints.gatekeeper.sh prohibit-role-wildcard-access -o yaml
kubectl get events -A | grep -i gatekeeper | grep -i wildcard || echo "OK"
```

---

# Вариант 2. **Patсh** существующего Constraint (добавить exemptions)

> Если у вас уже есть констрейнт (например, из Anthos Policy Essentials), проще добавить в него исключения.

```bash
# Патчим существующий констрейнт: добавляем exemptions.clusterRoles
# Подставьте <NAME> и, если есть, -n <NS>
kubectl patch k8sprohibitrolewildcardaccess.constraints.gatekeeper.sh <NAME> \
  --type merge -p '{
  "spec": {
    "parameters": {
      "exemptions": {
        "clusterRoles": [
          { "name": "^<YOUR_KIALI_FULLNAME>$",        "regexMatch": true },
          { "name": "^<YOUR_KIALI_FULLNAME>-viewer$", "regexMatch": true }

          // Или вместо двух строк — одна универсальная маска:
          // { "name": "^kiali(-viewer)?(-[a-z0-9-]+)?$", "regexMatch": true }
        ]
      }
    }
  }
}'
```

Проверка:

```bash
kubectl get k8sprohibitrolewildcardaccess.constraints.gatekeeper.sh <NAME> -o jsonpath='{.spec.parameters.exemptions}{"\n"}'
kubectl get events -A | grep -i gatekeeper | grep -i wildcard || echo "OK"
```

---

## Где взять `<YOUR_KIALI_FULLNAME>`

Это значение Helm-шаблона `{{ include "kiali-server.fullname" . }}`. Чаще всего оно равно **имени релиза** (`.Release.Name`). Узнать фактические имена ролей, созданных чартом, можно так:

```bash
# после деплоя чарта kiali-server
kubectl get clusterrole | grep -E 'kiali(-viewer)?$'
# либо посмотреть объект Application/Helm release:
helm -n <ns-kiali> list
helm -n <ns-kiali> get manifest <release> | grep -E '^kind: ClusterRole|^metadata:|name:'
```

Если видите, например, `kiali` и `kiali-viewer`, то в exemptions ставьте:

```yaml
- name: "^kiali$"
  regexMatch: true
- name: "^kiali-viewer$"
  regexMatch: true
```

---

## Проверка, что исключение сработало, а Kiali прошёл

1. Синканите/примените **Constraint** (или патч).
2. Синканите приложение **Kiali** с включённым:

   ```yaml
   rbac:
     create: true
   deployment:
     cluster_wide_access: true
   ```
3. Убедитесь, что роли создались и Gatekeeper их **не** отклонил:

   ```bash
   kubectl get clusterrole kiali kiali-viewer
   kubectl get events -A | grep -i gatekeeper | grep -i deny || echo "no denies"
   ```
4. Старт Kiali:

   ```bash
   kubectl -n <ns-kiali> get pods
   kubectl -n <ns-kiali> logs deploy/kiali --since=2m | egrep -i 'forbidden|denied|wildcard' || echo "RBAC OK"
   ```

---

## Советы по надёжности

* Если у вас несколько окружений/канареек, удобнее одна **универсальная regex-маска**:

  ```yaml
  - name: "^kiali(-viewer)?(-[a-z0-9-]+)?$"
    regexMatch: true
  ```

  Она покрывает `kiali`, `kiali-viewer`, `kiali-canary`, `kiali-viewer-canary` и т.п.

* **Не нужно** добавлять исключения для `ClusterRoleBinding` — правило запрещает wildcard именно в **Role/ClusterRole**.

* Если вы используете Kustomize/ArgoCD **multi-source**:

  * Политику (Constraint) отдайте **раньше** (sync-wave `-1`), чтобы во время синка RBAC уже попадали под нужные исключения.
  * Kiali (Helm) — `sync-wave 0`.

* Хотите «прогнать в сухую»: используйте `enforcementAction: dryrun` → в статусе констрейнта будут видны потенциальные нарушения, но применяться они не будут. После проверки верните `deny`.

---

Если напишешь фактические имена ролей Kiali, которые создаются у тебя Helm-чартом, я соберу точный YAML **exemptions** без regex (или с regex под ваши нейминг-правила), чтобы можно было просто положить файл в Git и синкнуть.
