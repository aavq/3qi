## Ключевая мысль — CRD не появляется, пока Gatekeeper-контроллер **успешно не скомпилирует** ваш `ConstraintTemplate` **и** не имеет прав создать CRD. Чаще всего виноваты:

1. **Ошибки Rego** (контроллер отказывается генерировать CRD) ([github.com][1]).
2. **Недостаточные RBAC-права** service-account’а Gatekeeper на `customresourcedefinitions` ([github.com][2]).
3. Контроллер ещё не успел создать CRD — нужно подождать состояние `Ready` шаблона ([github.com][3]).

Ниже пошаговая диагностика и возможные исправления.

---

## 1  Проверяем статус шаблона

```bash
kubectl get constrainttemplate k8stenantwildcardhost -o json | jq '.status'
```

* `created: true` — CRD **должен** быть; если его всё равно нет, смотрите права.
* `errors` / `byPod[*].errors` — покажут строки Rego, где компиляция провалилась ([github.com][4]).

  * Для Anthos 1.20 (Gatekeeper v3.11-) нет builtin-а `regex.escape_string`; такая строка даст **template\_ingest\_error** и CRD не создастся ([github.com][5]). Замените, например:

    ```rego
    safe := replace(suffix, ".", "\\.")
    ```

    или обновитесь до ≥ v3.13, где builtin уже есть.

---

## 2  Смотрим логи контроллера

```bash
kubectl -n gatekeeper-system logs deploy/gatekeeper-controller-manager -c manager \
  | grep k8stenantwildcardhost
```

* `compilation_error: undefined function` — исправляем Rego.
* `permission denied (create crd)` — добавляем ClusterRole:

```yaml
- apiGroups: ["apiextensions.k8s.io"]
  resources: ["customresourcedefinitions"]
  verbs: ["get","list","watch","create","update"]
```

Отсутствие этих прав описано в issue про «Unable to create CRD’s of constraints» ([github.com][2]).

---

## 3  Убедитесь, что дали контроллеру время

Gatekeeper создаёт CRD **асинхронно** после приёма шаблона ([github.com][6]).
В CI/CD добавьте ожидание:

```bash
kubectl apply -f k8stenantwildcardhost-template.yaml
kubectl wait --for=condition=Ready constrainttemplate/k8stenantwildcardhost --timeout=60s
kubectl apply -f k8stenantwildcardhost-constraint.yaml
```

Команда `kubectl wait` рекомендована авторами Gatekeeper для избежания гонки ([github.com][7]).

---

## 4  Проверяем сам CRD (когда всё заработает)

```bash
kubectl get crd k8stenantwildcardhosts.constraints.gatekeeper.sh -o wide
```

* Статусы `Established=True`, `NamesAccepted=True` должны быть **True** ([stackoverflow.com][8]).
* Если CRD есть, но Constraint всё равно не создаётся — убедитесь, что `kind` в Constraint совпадает с `names.kind` в Template, включая регистр символов ([github.com][9]).

---

## 5  Типовые сценарии исправления

| Симптом                                             | Действие                                                                                              |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `resource not found` сразу после `apply`            | Вставьте `kubectl wait` или sync-wave в Argo CD ([github.com][10])                                    |
| В логах `undefined function regex.escape_string`    | Уберите builtin или обновите Gatekeeper ≥ 3.13 ([github.com][1])                                      |
| В логах `permission denied while creating CRD`      | Расширьте ClusterRole S.A. Gatekeeper, как выше ([github.com][2])                                     |
| `created: true`, но Constraint всё ещё не видит CRD | Проверьте, нет ли другого контроллера, удаляющего CRD, и что Kind назван идентично ([github.com][11]) |

---

### Резюме

Появление CRD — обязательный индикатор успешной компиляции шаблона и достаточных прав Gatekeeper. Проверьте статус `.status`, логи контроллера, RBAC и версию Gatekeeper; после устранения причин команда `kubectl get crd k8stenantwildcardhosts.constraints.gatekeeper.sh` должна вернуть объект, а Constraint будет применяться без ошибок.

[1]: https://github.com/open-policy-agent/gatekeeper/issues/890?utm_source=chatgpt.com "Delete CRD when constraint template rego is invalid #890 - GitHub"
[2]: https://github.com/open-policy-agent/gatekeeper/issues/3457?utm_source=chatgpt.com "Unable to create CRD's of constraints and constraintTemplates ..."
[3]: https://github.com/open-policy-agent/gatekeeper/issues/1499?utm_source=chatgpt.com "No automated way to wait on constraint template CRD upgrades ..."
[4]: https://github.com/open-policy-agent/gatekeeper/issues/2053?utm_source=chatgpt.com "status.created is set to true even when all pods have reported errors"
[5]: https://github.com/open-policy-agent/gatekeeper/issues/756?utm_source=chatgpt.com "template_ingest_error when applying ConstraintTemplates on beta.11"
[6]: https://github.com/open-policy-agent/gatekeeper/issues/2047?utm_source=chatgpt.com "Deploy gatekeeper ConstraintTemplate and Constraint with flux #2047"
[7]: https://github.com/llvm/llvm-project/issues/145505?utm_source=chatgpt.com "[clang] `friend` declaration does not apply during constraint validation"
[8]: https://stackoverflow.com/questions/74238689/opa-rego-policy-pattern-matching-using-valid-regex-not-working?utm_source=chatgpt.com "OPA rego policy - pattern matching using valid regex not working"
[9]: https://github.com/open-policy-agent/gatekeeper/issues/1135?utm_source=chatgpt.com "Error in applying trusted-registries policy · Issue #1135 - GitHub"
[10]: https://github.com/argoproj/argo-cd/issues/9252?utm_source=chatgpt.com "Sync failed when deploy Gatekeeper ConstraintTemplate ... - GitHub"
[11]: https://github.com/open-policy-agent/gatekeeper/issues/677?utm_source=chatgpt.com "CRDs for Constraints and ConstraintTemplates should have ..."
