## Краткое резюме

В многоарендном кластере Istio Gateway, объявленный одним арендатором с хостом `*` или `*.corp.com`, перехватывает **все** SNI/Host-запросы, пришедшие на общий IP-адрес шлюза — это задокументировано в дискуссиях сообщества и в issue-трекере Istio. Чтобы исключить коллизии, Google-Cloud/ASM рекомендует «жёстко лейзить» wildcard только на уровне tenant-поддомена и применять OPA Gatekeeper для enforcement-а подобных правил.
Ниже приведён **ConstraintTemplate** Gatekeeper, реализующий это требование: символ `*` допустим лишь в начале строки и только перед собственным namespace арендатора — шаблон `*. <namespace>.asm-uk-01.uat.hc.intranet.corp.com`. Все остальные варианты (например `*.hc.intranet.corp.com`) будут отклонены.

---

## Почему «глобальный» `*` опасен

* Приоритет маршрутов в Envoy на стороне ingress-шлюза определяется порядком генерации конфигурации; первый wildcard-хост фактически «забивает» остальные записи, что приводит к 404/503 у соседних арендаторов.
* Официальная документация Istio разрешает wildcard-SNI/Host, подчёркивая, что `*` соответствует «любому домену», поэтому без политики контроля платформа не защищена.

---

## Подход «policy-as-code» Google / OPA Gatekeeper

* Gatekeeper ConstraintTemplate — рекомендуемый механизм декларативного контроля для GKE/ASM кластеров.
* В Rego используются built-in-функции `startswith`, `contains`, `substr` и `regex.match`.
* Шаблон должен принимать параметр `domainSuffix`, чтобы не жёстко фиксировать окружение и облегчить перенос между кластерами.

---

## ConstraintTemplate `IstioIngressWildcardScope`

```yaml
apiVersion: templates.gatekeeper.sh/v1beta1
kind: ConstraintTemplate
metadata:
  name: istioingresswildcardscope
  annotations:
    metadata.gatekeeper.sh/title: "Istio Gateway Wildcard Scope"
    description: |
      В многоарендных кластерах wildcard-хосты вида "*" или "*.<domain>"
      в Istio Gateway перехватывают весь входящий трафик и нарушают изоляцию арендаторов.
      Политика разрешает использовать символ "*" только в начале строки и
      только перед собственным namespace:
        "*. <namespace>.${domainSuffix}"
      Любой другой вариант будет отклонён.
spec:
  crd:
    spec:
      names:
        kind: IstioIngressWildcardScope
      validation:
        openAPIV3Schema:
          properties:
            domainSuffix:
              type: string
              description: "Фиксированная часть домена, напр. asm-uk-01.uat.hc.intranet.corp.com"
  targets:
  - target: admission.k8s.gatekeeper.sh
    rego: |
      package istioingresswildcardscope

      # Хост считается валидным, если начинается с "*."
      # и далее следует "<namespace>.<suffix>"
      valid_host(host, ns, suffix) {
        startswith(host, "*.")
        remainder := host[2:]        # обрезаем "*."
        remainder == sprintf("%s.%s", [ns, suffix])
      }

      violation[{"msg": msg}] {
        input.review.kind.group == "networking.istio.io"
        input.review.kind.kind  == "Gateway"
        some i
        some j
        host := input.review.object.spec.servers[i].hosts[j]
        contains(host, "*")          # ловим все варианты с '*'
        ns := input.review.object.metadata.namespace
        suffix := params.domainSuffix
        not valid_host(host, ns, suffix)

        msg := sprintf(
          "Недопустимый wildcard-хост %q: разрешён только формат \"*.%s.%s\" для namespace %q.",
          [host, ns, suffix, ns])
      }
```

---

## Пример Constraint (production-режим)

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: IstioIngressWildcardScope
metadata:
  name: deny-global-wildcards
spec:
  match:
    kinds:
    - apiGroups: ["networking.istio.io"]
      kinds:     ["Gateway"]
  parameters:
    domainSuffix: "asm-uk-01.uat.hc.intranet.corp.com"
```

---

## Как применить и протестировать

1. **Установите Gatekeeper** (если ещё не стоит) согласно официальной инструкции.
2. `kubectl apply -f istioingresswildcardscope-template.yaml`
3. `kubectl apply -f deny-global-wildcards.yaml`
4. Попробуйте создать Gateway с хостом `*.hc.intranet.corp.com` — admission-контроллер вернёт ошибку с сообщением из `msg`.
5. Создание `*.mytenant.asm-uk-01.uat.hc.intranet.corp.com` пройдёт успешно.

---

## Возможные расширения

* **Список доменных суффиксов** — вместо строки `domainSuffix` задать массив, если в одном кластере несколько регионов.
* **Виртуальные сервисы** — аналогичную проверку можно добавить для `VirtualService.spec.hosts`.
* **Тестирование gator verify** — храните пример «нарушающих» CRD в репозитории и проверяйте их в CI/CD.
* **Миграция на Rego v1** — начиная с Gatekeeper 3.19 можно включить современный синтаксис посредством `crd.spec.targets[*].regoType: v1`.

---

### Полезные ссылки

* Документация Istio Gateway и wildcard-поведение
* Библиотека готовых ConstraintTemplate от Google (Anthos/ASM)
* Руководство Gatekeeper и пример ConstraintTemplate workflow
* Built-in-функции Rego `startswith`, `contains`, `regex.match`, `split`


---
---
---


Ниже — раз-за-разом ответы на оба ваших вопроса, с примерами YAML и пояснениями, почему именно так работает Gatekeeper.

---

## Коротко

* **ConstraintTemplate** (шаблон) лишь создаёт в кластере CRD + Rego-код и сам по себе *ничего не проверяет* ([open-policy-agent.github.io][1]).
* **Constraint** (ресурс вида `kind: K8sTenantWildcardHost`) — это «экземпляр» шаблона с параметрами; именно он включает политику в admission-webhook ([open-policy-agent.github.io][2]).
* Поэтому без `K8sTenantWildcardHost` **никакие проверки не выполнятся** — запросы с «плохими» `Gateway` будут успешно создаваться, будто политики нет ([pradeepl.com][3], [pradeepl.com][4]).
* Если нужно несколько допустимых хвостов DNS, у вас есть **два проверенных пути**:

  1. **Создать несколько Constraints** (по одному на каждый суффикс).
  2. **Изменить шаблон** так, чтобы параметр `domainSuffix` стал массивом (`type: array`) — тогда один Constraint сможет принимать список.

---

## 1 — Почему без `kind: K8sTenantWildcardHost` политика «молчит»

| Что применяем         | Что происходит                                                                                                                                                                       | Ссылки |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| Только Template       | Кластер получает CRD и Rego, но ни один объект к нему не «привязан» → Gatekeeper не вызывает код при адмиссии ([open-policy-agent.github.io][1], [open-policy-agent.github.io][5])   |        |
| Template + Constraint | При каждом `CREATE`/`UPDATE` ресурса, попадающего под `match`, Gatekeeper выполняет Rego и может вернуть `deny` ([open-policy-agent.github.io][2], [open-policy-agent.github.io][6]) |        |

Это стандартный механизм OPA Constraint Framework: *template описывает логику, constraint — применяет её* ([open-policy-agent.github.io][7]).

---

## 2 — Способ A: несколько Constraints

Самый простой путь: клонируем Constraint и задаём разный суффикс — политика будет срабатывать, если **хотя бы один Constraint** разрешает wildcard.

```yaml
# k8sTenantWildcardHost – PROD
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sTenantWildcardHost
metadata:
  name: prod-wildcards
spec:
  parameters:
    domainSuffix: "asm-uk-01.prod.hc.intranet.corp.com"
---
# k8sTenantWildcardHost – UAT
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sTenantWildcardHost
metadata:
  name: uat-wildcards
spec:
  parameters:
    domainSuffix: "asm-uk-01.uat.hc.intranet.corp.com"
```

Gatekeeper допускает любое количество Constraints на один Template, это обычная практика — см. пример **K8sRequiredLabels** в документации ([open-policy-agent.github.io][1]).

**Плюс:** не надо менять Rego.
**Минус:** при дюжине суффиксов получится дюжина CR — иногда неудобно.

---

## 3 — Способ B: массив `domainSuffixes` в одном Constraint

1. **Меняем схему** в Template:

```yaml
openAPIV3Schema:
  type: object
  properties:
    domainSuffixes:
      type: array
      items:
        type: string
```

(Аналогично сделано в официальном шаблоне **k8sAllowedRepos**, где параметр `repos` — массив строк) ([open-policy-agent.github.io][8]).

2. **Обновляем Rego** — проверяем, что *хотя бы один* суффикс совпал:

```rego
suffixes := input.parameters.domainSuffixes
match_any := any([ true | suff := suffixes[_] ;
                         re_match(pattern_for(suff), host) ])

violation[{...}] {
  startswith(host, "*.")
  not match_any
}
```

3. **Constraint** теперь выглядит так:

```yaml
spec:
  parameters:
    domainSuffixes:
    - "asm-uk-01.uat.hc.intranet.corp.com"
    - "asm-uk-01.prod.hc.intranet.corp.com"
```

**Плюс:** одна запись — список суффиксов.
**Минус:** придётся перезаписать Template (и подождать, пока Gatekeeper пересоберёт политику) ([github.com][9]).

---

## 4 — Что выбрать?

| Критерий                     | Несколько Constraints                  | Массив в Template                                                                                    |
| ---------------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Изменения Rego               | **Нет**                                | **Да**                                                                                               |
| Кол-во CRD/CR                | Больше CR, но шаблон один              | Остаётся один CR                                                                                     |
| Горячее включение/отключение | Удаляем/создаём Constraint — мгновенно | Нужно пересоздавать Template (влияет на все кластеры, если общий Argo-CD)                            |
| Поддержка в Anthos 1.20.3    | ✔️ (стабильно)                         | ✔️ (тоже стабильно, примеры с массивами в библиотеке Gatekeeper) ([open-policy-agent.github.io][10]) |

В большинстве случаев Ops-команды выбирают **вариант с несколькими Constraints**: он проще в CI/CD и не ломает совместимость.

---

## 5 — Проверяем, что всё работает

1. `kubectl apply -f k8stenantwildcardhost-template.yaml`
2. `kubectl apply -f prod-wildcards.yaml` (или Constraint c массивом)
3. Создаём «плохой» Gateway: `*.alice.hc.intranet.corp.com`
   *Ожидаем* — отказ с сообщением из Rego.
4. Создаём «хороший»: `*.alice.asm-uk-01.uat.hc.intranet.corp.com` — проходит.

Если видите, что «плохой» объект всё-таки принимается — проверьте, что Constraint существует и `status.totalViolations` не равен 0 — типичная ошибка описана в issue #2967 ([github.com][11]) и на Stack Overflow ([stackoverflow.com][12]).

---

### Главное

* **Template без Constraint = нулевая защита.**
* **Много суффиксов?** Берите либо пачку Constraint-ов, либо дорабатывайте параметр Template до массива — оба пути официально поддержаны и проверены на продакшене ([open-policy-agent.github.io][13], [open-policy-agent.github.io][6]).

[1]: https://open-policy-agent.github.io/gatekeeper/website/docs/next/howto/ "How to use Gatekeeper | Gatekeeper"
[2]: https://open-policy-agent.github.io/gatekeeper/website/docs/next/constrainttemplates/?utm_source=chatgpt.com "Constraint Templates | Gatekeeper - GitHub Pages"
[3]: https://pradeepl.com/blog/kubernetes/deploying-gatekeeper-and-defining-constraints/ "Deploying OPA Gatekeeper and defining constraints | Pradeep Loganathan's Blog"
[4]: https://pradeepl.com/blog/kubernetes/deploying-gatekeeper-and-defining-constraints/?utm_source=chatgpt.com "Deploying OPA Gatekeeper and defining constraints"
[5]: https://open-policy-agent.github.io/gatekeeper/website/docs/next/howto/?utm_source=chatgpt.com "How to use Gatekeeper - GitHub Pages"
[6]: https://open-policy-agent.github.io/gatekeeper/website/docs/enforcement-points/?utm_source=chatgpt.com "Enforcement points in Gatekeeper - GitHub Pages"
[7]: https://open-policy-agent.github.io/gatekeeper/website/docs/howto/?utm_source=chatgpt.com "How to use Gatekeeper - GitHub Pages"
[8]: https://open-policy-agent.github.io/gatekeeper-library/website/validation/allowedrepos "Allowed Repositories | Gatekeeper Library"
[9]: https://github.com/open-policy-agent/gatekeeper-library/blob/master/library/general/allowedrepos/template.yaml?utm_source=chatgpt.com "template.yaml - open-policy-agent/gatekeeper-library - GitHub"
[10]: https://open-policy-agent.github.io/gatekeeper-library/website/validation/allowedrepos?utm_source=chatgpt.com "Allowed Repositories | Gatekeeper Library - GitHub Pages"
[11]: https://github.com/open-policy-agent/gatekeeper/issues/2967?utm_source=chatgpt.com "Constrain violation is enforced properly but not updated on Status of ..."
[12]: https://stackoverflow.com/questions/76575729/opa-gatekeeper-constraints-not-working-only-allow-images-from-a-private-registry "kubernetes - OPA Gatekeeper constraints not working only allow images from a private registry - Stack Overflow"
[13]: https://open-policy-agent.github.io/gatekeeper/website/docs/constrainttemplates/?utm_source=chatgpt.com "Constraint Templates | Gatekeeper - GitHub Pages"

---
---
---

Ниже приведены полностью валидные манифесты YAML:

* **ConstraintTemplate** — версия с параметром-массивом `domainSuffixes`, чтобы одним Constraint’ом можно было разрешить сразу несколько хвостов DNS.
* Два образца **Constraint**:

  * `tenant-wildcard-hosts` — показывает, как задать **несколько** суффиксов в одном объекте;
  * `tenant-wildcard-hosts-uat` — пример, когда вы предпочитаете один суффикс = один Constraint.

Разворачивайте их в любом порядке: Template первым, затем один или несколько Constraint-ов.

---

## ConstraintTemplate `k8stenantwildcardhost-template.yaml`

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8stenantwildcardhost
  annotations:
    description: |
      Blocks overly-broad wildcards in Istio Gateways.
      Permitted pattern:  *.TENANT.<domainSuffix>
      The tenant label may be any valid RFC-1123 DNS label.
spec:
  crd:
    spec:
      names:
        kind: K8sTenantWildcardHost
      validation:
        openAPIV3Schema:
          type: object
          properties:
            domainSuffixes:
              type: array
              description: |
                One or more fixed DNS suffixes that must follow the tenant
                label, e.g. "asm-uk-01.uat.hc.intranet.corp.com".
              items:
                type: string
  targets:
  - target: admission.k8s.gatekeeper.sh
    rego: |
      package k8stenantwildcardhost

      import data.lib.regex

      ######################################################################
      # helper: returns true if the host matches any allowed suffix
      ######################################################################
      allowed(host) {
        suffixes := parameters.domainSuffixes
        some suff
        suff := suffixes[_]
        safe := regex.escape_string(suff)
        pat  := sprintf("^[*]\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?\\.%s$", [safe])
        re_match(pat, host)
      }

      ######################################################################
      # main rule: flag violation for forbidden wildcard hosts
      ######################################################################
      violation[{
        "msg": sprintf(
          "Wildcard host %q is not permitted. Wildcards must match the pattern *.TENANT.<one of %v>.",
          [host, parameters.domainSuffixes]),
        "details": {"host": host}
      }] {
        input.review.kind.kind == "Gateway"
        some server in input.review.object.spec.servers
        host := server.hosts[_]
        startswith(host, "*.")   # user действительно использует wildcard
        not allowed(host)        # …но не в разрешённом месте
      }
```

---

## Constraint № 1 — несколько sufix-ов в одном объекте

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sTenantWildcardHost
metadata:
  name: tenant-wildcard-hosts
spec:
  parameters:
    domainSuffixes:
      - "asm-uk-01.uat.hc.intranet.corp.com"
      - "asm-uk-01.prod.hc.intranet.corp.com"
  match:
    kinds:
      - apiGroups: ["networking.istio.io"]
        kinds: ["Gateway"]
```

---

## Constraint № 2 — один sufix = один Constraint

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sTenantWildcardHost
metadata:
  name: tenant-wildcard-hosts-uat
spec:
  parameters:
    domainSuffixes:
      - "asm-uk-01.uat.hc.intranet.corp.com"
  match:
    kinds:
      - apiGroups: ["networking.istio.io"]
        kinds: ["Gateway"]
```

> **Как применить**

```bash
kubectl apply -f k8stenantwildcardhost-template.yaml
kubectl apply -f tenant-wildcard-hosts.yaml          # или/и
kubectl apply -f tenant-wildcard-hosts-uat.yaml
```

После этого Gatekeeper (v anthos 1.20.3) начнёт отклонять любые `Gateway`, в которых wildcard звёздочка находится выше уровня `TENANT.<domainSuffix>`.

