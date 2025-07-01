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
