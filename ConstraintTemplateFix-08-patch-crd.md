### Сводка одним абзацем

Argo CD показывает diff для ресурса **K8sTenantWildcardHost**, потому что Kubernetes-API во время приёма объекта обрезает поле `spec.match`: оно отсутствует в схемe CRD, которую Gatekeeper ≤ v3.12 генерирует на основе ConstraintTemplate. Из-за этого в etcd хранится объект без `match`, а в Git он есть — Argo фиксирует расхождение и ставит `OutOfSync`. Исправить можно тремя способами: обновить Gatekeeper до ≥ v3.13, пропатчить сгенерированный CRD добавкой `x-kubernetes-preserve-unknown-fields: true`, либо научить Argo CD игнорировать поле `match`. Ниже подробности.

---

## Почему так происходит

1. **Gatekeeper генерирует CRD** только с описанием `spec.parameters`; у корня `spec` выставлен `preserveUnknownFields=false`.
2. **Kubernetes** приёмом ресурса сравнивает его со схемой и отбрасывает поля, которых нет в схеме (принцип pruning).
3. **Argo CD** сравнивает YAML из Git c live-объектом из etcd: видит, что `match` отсутствует, и отмечает diff.

---

## Способ A — обновить Gatekeeper ≥ v3.13

В этих версиях генератор CRD добавляет `x-kubernetes-preserve-unknown-fields: true` ко всему `spec`, и Kubernetes перестаёт обрезать «лишние» поля. Нужно:

1. Обновить Anthos-канал или установить community-релиз Gatekeeper ≥ v3.13.
2. Пересоздать ConstraintTemplate (CRD пересоздастся автоматически).
3. Сделать `argocd app sync` — статус станет **Synced**.

---

## Способ B — патч CRD (без апгрейда Gatekeeper)

1. Создайте файл `patch-crd.yaml`:

   ```yaml
   apiVersion: apiextensions.k8s.io/v1
   kind: CustomResourceDefinition
   metadata:
     name: k8stenantwildcardhosts.constraints.gatekeeper.sh
   spec:
     validation:
       openAPIV3Schema:
         x-kubernetes-preserve-unknown-fields: true
   ```
2. Добавьте патч в тот же репозиторий, где манифесты Gatekeeper, и задайте `sync-wave: "1"` (или PreSync-hook), чтобы патч применялся сразу после шаблона.
3. `argocd app sync` → CRD допатчится, `match` сохранится, diff исчезнет.

---

## Способ C — игнор diff в Argo CD

Если менять кластер нельзя, добавьте к Application аннотацию:

```yaml
metadata:
  annotations:
    argocd.argoproj.io/ignore-differences: |
      jsonPointers:
      - /spec/match
```

Argo перестанет сравнивать поле `match`; приложение будет **Synced**, но фактического хранeния `match` в etcd по-прежнему не будет.

---

### Что выбрать

* Хотите «правильно и навсегда» — **обновите Gatekeeper** (вариант A).
* Не можете обновить — **патч CRD** (вариант B) — единственное решение, при котором `spec.match` действительно сохранится в объекте.
* Нужно быстро и достаточно «косметически» — аннотация `ignore-differences` (вариант C).

После применения варианта A или B проверьте:

```bash
kubectl get crd k8stenantwildcardhosts.constraints.gatekeeper.sh \
  -o jsonpath='{.spec.validation.openAPIV3Schema.x-kubernetes-preserve-unknown-fields}'
# должно вывести true

kubectl get k8stenantwildcardhost <имя> -o yaml | yq '.spec.match'
# блок match должен присутствовать
```

Теперь Argo CD больше не будет видеть diffs, и статус приложения станет **Synced**.


---
---
---


Никакой новой CRD создавать не нужно – она уже есть, вам нужно **пропатчить существующую**.
Ошибка `unknown field "spec. validation"` появилась потому, что:

1. вы отправили манифест как *«create»* (API-сервер пытается трактовать его как полноценную CRD, а не как patch);
2. в YAML после `spec.` случайно попала пробельная строка, из-за чего key `validation` распознался неправильно.

Ниже два надёжных способа внести флаг `x-kubernetes-preserve-unknown-fields: true` в уже-созданный CRD.

---

## Способ 1 — однократный patch через команду

```bash
kubectl patch crd k8stenantwildcardhosts.constraints.gatekeeper.sh \
  --type='merge' \
  -p='{"spec":{"validation":{"openAPIV3Schema":{"x-kubernetes-preserve-unknown-fields":true}}}}'
```

* тип **merge** – самый простой: он «смешивает» ваш JSON-фрагмент со
  структурой объекта;
* подтверждение увидите в поле `patched` → `true`;
* после этого `kubectl get` покажет, что флаг установлен, а Argo CD
  перестанет видеть diff.

---

## Способ 2 — declarative patch-файл + apply

1. Создайте файл `crd-preserve-patch.yaml`:

   ```yaml
   apiVersion: apiextensions.k8s.io/v1
   kind: CustomResourceDefinition
   metadata:
     name: k8stenantwildcardhosts.constraints.gatekeeper.sh
   spec:
     validation:
       openAPIV3Schema:
         x-kubernetes-preserve-unknown-fields: true
   ```

2. Примените **apply**, а не create:

   ```bash
   kubectl apply -f crd-preserve-patch.yaml
   ```

   `kubectl` распознает, что объект уже существует, и выполнит
   стратегический merge.

> Важно: убедитесь, что в файле *нет* пробелов между `spec.` и `validation`
> (должно быть именно `spec:`, затем следующий уровень `validation:`).

---

## Проверка

```bash
# Флаг должен быть true
kubectl get crd k8stenantwildcardhosts.constraints.gatekeeper.sh \
  -o jsonpath='{.spec.validation.openAPIV3Schema.x-kubernetes-preserve-unknown-fields}'

# Блок match теперь хранится
kubectl get k8stenantwildcardhost tenant-wildcard-hosts -o yaml | yq '.spec.match'
```

Если оба вывода корректные, Argo CD после следующего `Sync / Refresh`
отобразит приложение как **Synced**.

---

### Почему не сработал предыдущий вариант «добавить в Template»

Gatekeeper копирует из `ConstraintTemplate` только под-раздел
`spec.parameters`, всё остальное (включая ваш `match`) в итоговый CRD не
попадает. Поэтому единственный путь на Gatekeeper ≤ v3.12 – править сам CRD
(описано выше) либо обновиться до Gatekeeper v3.13+, где флаг ставится
автоматически.


---
---
---


### Что происходит — почему diff не исчез после patch

1. **Параметр `x-kubernetes-preserve-unknown-fields: true` теперь действительно стоит**
   (команда `kubectl patch …` вернула `patched (no change)` → флаг был уже `true`).

2. **Live-объекты, созданные *до патча*, всё-равно хранятся в etcd без `spec.match`**.
   API-server обрезал поле в тот момент, когда CRD ещё был “узким”.
   Изменение схемы *не ретроактивно*: Kubernetes **не переписывает старые объекты**.

3. Argo CD при diff берёт YAML из Git (с `match`) и сравнивает с **текущей копией
   объекта в etcd** (без `match`) → diff остаётся.

---

### Шаги, чтобы diff ушёл

| Шаг                                               | Команда                                                                                                             | Зачем                                                                    |                               |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ----------------------------- |
| 1. Пересоздать или пере-apply Constraint          | `bash kubectl delete k8stenantwildcardhost tenant-wildcard-hosts && \ kubectl apply -f tenant-wildcard-hosts.yaml ` | Новый ресурс пройдёт через **обновлённый** CRD, поле `match` сохранится. |                               |
| 2. Убедиться, что `match` реально лежит в объекте | \`\`\`bash kubectl get k8stenantwildcardhost tenant-wildcard-hosts -o yaml                                          | yq '.spec.match' \`\`\`                                                  | Должен показать блок `kinds`. |
| 3. Обновить состояние в Argo CD                   | `argocd app sync <app>` или просто **Refresh**                                                                      | Argo перечитает live-объект, diff исчезнет, статус станет **Synced**.    |                               |

> **Важно:** если у вас несколько Constraint-ов этого шаблона, повторите delete/apply для каждого или выполните `kubectl rollout restart deployment/…` в Helm/Argo CD, чтобы они пересоздались автоматически.

---

### Почему не надо больше ничего менять в схеме

* Флаг `x-kubernetes-preserve-unknown-fields: true` на корневом
  `openAPIV3Schema` уже гарантирует, что **любые неизвестные поля** внутри
  `spec` (включая массивы) будут сохраняться со следующего создания.
* Дописывать вручную свойства `match.kinds` не требуется; достаточно
  перезаписать сами объекты, чтобы они «завелись» под новой схемой.

---

### Проверка, что всё сделано

```bash
# 1. Флаг сохранён
kubectl get crd k8stenantwildcardhosts.constraints.gatekeeper.sh \
  -o jsonpath='{.spec.validation.openAPIV3Schema.x-kubernetes-preserve-unknown-fields}'
# → true

# 2. Новый объект содержит match
kubectl get k8stenantwildcardhost tenant-wildcard-hosts -o yaml | yq '.spec.match.kinds[0]'
# → должен показать apiGroups и kinds

# 3. Argo CD
argocd app get <app> | grep Status
# → Status: Synced
```

Если все три проверки проходят, проблема diff окончательно решена.



