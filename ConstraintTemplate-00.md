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
