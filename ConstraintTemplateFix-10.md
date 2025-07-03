## Суть доработки

Политика должна блокировать **два** варианта:

1. Wildcard «выше уровня tenant» — как и раньше (`*.alice.hc.intranet…`).
2. Полный захват `hosts: ["*"]`, когда звёздочка стоит без точки.

Чтобы учесть второй случай, в условие `violation` добавляем проверку `host == "*"`. Логика «разрешён ли host» не меняется.

---

## Обновлённый фрагмент Rego

```rego
package k8stenantwildcardhost

# -------------------------------------------------------------------
# helper: true, если host удовлетворяет хотя бы одному <suffix>
# -------------------------------------------------------------------
valid_host(host) {
  suffix := input.parameters.domainSuffixes[_]
  safe   := replace(suffix, ".", "\\.")
  pattern := sprintf("^[*]\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?\\.%s$", [safe])
  re_match(pattern, host)
}

# -------------------------------------------------------------------
# основное правило – формируем violation
# -------------------------------------------------------------------
violation[{ "msg": msg }] {
  input.review.kind.kind == "Gateway"

  server := input.review.object.spec.servers[_]
  host   := server.hosts[_]

  # ❌ 1) звёздочка без точки  ИЛИ  ❌ 2) wildcard выше tenant-уровня
  (host == "*"  ; msg := sprintf("Полный wildcard %q запрещён – он перехватывает весь трафик.", [host]))  |
  (startswith(host, "*.") ; not valid_host(host)
      ; msg := sprintf(
          "Wildcard host %q запрещён. Разрешён только формат *.TENANT.<suffix>, где <suffix> входит в %v.",
          [host, input.parameters.domainSuffixes]))
}
```

### Что изменилось

* `host == "*"` — ловит запись с одиночной звёздочкой.
* Оператор `|` в блоке `violation` даёт два альтернативных сообщения:

  * если сработало условие «полный wildcard» — выводится короткое пояснение;
  * если wildcard «выше tenant-уровня» — остаётся прежнее подробное сообщение.

---

## Как применить

1. Обновите файл ConstraintTemplate, заменив секцию `rego:` на код выше.
2. `kubectl apply -f k8stenantwildcardhost-template.yaml`
3. Дождитесь `Ready` (или подождите пару секунд) – Gatekeeper пересоберёт политику.

Теперь:

* `hosts: ["*"]` – будет отклонён с сообщением «Полный wildcard \* запрещён…».
* `hosts: ["*.alice.hc.intranet.corp.com"]` – тоже отклонён.
* `hosts: ["*.alice.asm-uk-01.uat.hc.intranet.corp.com"]` – допустим.

Политика покрывает оба критических сценария и по-прежнему допускает `*.TENANT.<suffix>`.
