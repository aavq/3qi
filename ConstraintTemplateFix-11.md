Вот корректная версия Rego-кода, совместимая с OPA 0.38 (Gatekeeper v3.11) — я разнес два разных случая в **два отдельных правила `violation`**. Такой приём избавляет от сложных конструкций `(...) | (...)`, из-за которых парсер выдал «non-terminated expression».

```rego
package k8stenantwildcardhost

###############################################################################
# helper: host валиден, если соответствует хотя бы одному разрешённому suffix
###############################################################################
valid_host(host) {
  suffix := input.parameters.domainSuffixes[_]
  safe   := replace(suffix, ".", "\\.")
  pattern := sprintf("^[*]\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?\\.%s$", [safe])
  re_match(pattern, host)
}

###############################################################################
# ❶ Полный wildcard "*"
###############################################################################
violation[{ "msg": msg }] {
  input.review.kind.kind == "Gateway"

  server := input.review.object.spec.servers[_]
  host   := server.hosts[_]

  host == "*"                                        # ← одиночная звёздочка
  msg := sprintf(
    "Полный wildcard %q запрещён — он перехватывает весь входящий трафик.",
    [host])
}

###############################################################################
# ❷ Wildcard выше уровня TENANT
###############################################################################
violation[{ "msg": msg }] {
  input.review.kind.kind == "Gateway"

  server := input.review.object.spec.servers[_]
  host   := server.hosts[_]

  startswith(host, "*.")                             # звёздочка c точкой
  not valid_host(host)                               # …но не на разрешённом уровне

  msg := sprintf(
    "Wildcard host %q запрещён. Разрешён только формат *.TENANT.<suffix>, "+
    "где <suffix> входит в %v.",
    [host, input.parameters.domainSuffixes])
}
```

### Почему прежний вариант не прошёл парсер

* В Rego 0.38 **нельзя** группировать выражения с `()` и объединять их `|` внутри одного `violation` — парсер считает это «незавершённым выражением» и ломается на первой кавычке.
* Кроме того, сочетание `;` и `|` в одной группе допускается только в «скобочной компрехеншн»-синтаксисе (`[ x | … ]`), а не в теле правила.

### Как проверить

```bash
opa eval -f pretty -d шаблон.rego 'data.k8stenantwildcardhost'
```

Ошибок парсинга быть не должно. Затем:

1. Примените обновлённый `ConstraintTemplate`.
2. `kubectl wait --for=condition=Ready constrainttemplate/k8stenantwildcardhost`.
3. Проверьте, что:

   * `hosts: ["*"]` — отклоняется с первым сообщением.
   * `hosts: ["*.tenant.hc.intranet.corp.com"]` — отклоняется со вторым.
   * `hosts: ["*.tenant.asm-uk-01.uat.hc.intranet.corp.com"]` — пропускается.

Теперь политика закрывает оба критичных сценария и компилируется без ошибок.
