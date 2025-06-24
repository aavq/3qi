Ошибка рас-парсинга говорит ровно о том, что Rego-движок внутри вашей сборки Gatekeeper **не понимает современный синтаксис**

```rego
some server in input.review.object.spec.servers
```

> ```
> rego_parse_error: unexpected ident token …
> (hint: `import future.keywords.in` for `some x in xs` expressions)
> ```

### Почему так происходит

* Форма «`some x in xs`» появилась в OPA ≥ 0.46 и по-умолчанию включается только
  если добавить строку
  `import future.keywords.in`  — иначе парсер считает слово **`in`**
  лишним.
* В Gatekeeper v3.11 (именно он входит в **anthos 1.20.3**) используется OPA 0.38,
  в котором ни этого синтаксиса, ни директивы `future.keywords` ещё нет.

Поэтому шаблон нужно переписать в «старом» стиле — через индексирование
`array[_]`.

---

## Быстрое исправление Rego-части

Ниже минимальный фрагмент, совместимый с OPA 0.38/0.39:

```rego
package k8stenantwildcardhost

###############################################################################
# Хелпер: проверка, что host соответствует любому suffix из списка
###############################################################################
allowed(host) {
  suffixes := parameters.domainSuffixes
  suff := suffixes[_]                     #   ← старый стиль перебора
  safe := replace(suff, ".", "\\.")       #   экранируем точки
  pat  := sprintf("^[*]\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?\\.%s$", [safe])
  re_match(pat, host)
}

###############################################################################
# Основное правило
###############################################################################
violation[msg] {
  input.review.kind.kind == "Gateway"

  server := input.review.object.spec.servers[_]   # вместо `some … in …`
  host   := server.hosts[_]

  startswith(host, "*.")
  not allowed(host)

  msg := sprintf(
    "Wildcard host %q is not permitted. Wildcards must match pattern *.TENANT.<one of %v>.",
    [host, parameters.domainSuffixes])
}
```

### Что изменено

| Было                                             | Стало                       |
| ------------------------------------------------ | --------------------------- |
| `some server in array`                           | `server := array[_]`        |
| `some suff in suffixes`                          | `suff := suffixes[_]`       |
| `regex.escape_string()` (недоступна до OPA 0.43) | `replace(suff, ".", "\\.")` |

---

## Дальнейшие шаги

1. **Отредактируйте ConstraintTemplate** (Rego-секцию — см. выше).
2. `kubectl apply -f k8stenantwildcardhost-template.yaml`
3. Убедитесь, что теперь статус шаблона показывает `created: true`:

   ```bash
   kubectl get constrainttemplate k8stenantwildcardhost -o=jsonpath='{.status.created}'
   ```
4. Проверьте появление CRD:

   ```bash
   kubectl get crd k8stenantwildcardhosts.constraints.gatekeeper.sh
   ```
5. После этого можно применять сам Constraint — ошибка «resource not found»
   больше не проявится.

---

### Альтернатива — обновить Gatekeeper

Если хотите пользоваться новым синтаксисом **без** переписывания кода, нужно
перейти на Gatekeeper ≥ v3.14 (OPA 0.46+).
Для Anthos это означает обновление до более свежего канала или ручную установку community-билда Gatekeeper.
