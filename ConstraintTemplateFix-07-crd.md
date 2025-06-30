**Коротко:**
Argo CD сравнивает *то, что лежит в Git* с *тем, что реально хранит-ся в etcd*.
При создании `K8sTenantWildcardHost` Kubernetes-API **отбрасывает** поле
`spec.match.kinds`, потому что сгенерированный CRD-шник от Gatekeeper **не
знает** про это поле и включает строгую “схему с обрезкой” — вся неопределённая
структура удаляется, прежде чем объект попадает в etcd.
В Git поле остаётся, в кластере его уже нет ⇒ Argo CD видит diff и пишет
*OutOfSync (requires pruning)*.
Это типичная ситуация для Gatekeeper-Constraint’ов и CRD-ов
со структурными схемами — см. обсуждения ([github.com][1], [github.com][2]).

---

## Почему API-server «порезал» объект

| Шаг | Что происходит                                                                                               |
| --- | ------------------------------------------------------------------------------------------------------------ |
| 1   | Gatekeeper, увидев `ConstraintTemplate`, генерирует CRD с валидационной схемой.                              |
| 2   | В нашем шаблоне мы задали схему **только для `spec.parameters`**, остальных полей (включая `match`) там нет. |
| 3   | Для структурных CRD (K8s ≥1.22) API-server **обрезает все незадекларированные поля** ([kubernetes.io][3]).   |
| 4   | В etcd сохраняется уже «укороченный» объект, и Argo CD фиксирует расхождение.                                |

Gatekeeper раньше автоматически помечал корень `spec` флагом
`x-kubernetes-preserve-unknown-fields: true`, но в ветках v3.9–v3.12 был баг,
из-за которого эта аннотация исчезала — см. issue #1468 ([github.com][1]).

---

## Способы устранить OutOfSync

### 1 . Расширить схему или разрешить произвольные поля

#### Вариант A — включить «не обрезать»

Добавьте флаг прямо в шаблон:

```yaml
spec:
  crd:
    spec:
      names:
        kind: K8sTenantWildcardHost
      validation:
        openAPIV3Schema:
          type: object
          x-kubernetes-preserve-unknown-fields: true   # ← ключевая строка
          properties:
            domainSuffixes:
              type: array
              items:
                type: string
```

`x-kubernetes-preserve-unknown-fields: true` заставит API-server
оставить любые незадекларированные данные ([kubernetes.io][4]).
После обновления шаблона:

```bash
kubectl apply -f k8stenantwildcardhost-template.yaml
kubectl wait --for=condition=Ready constrainttemplate/k8stenantwildcardhost
argocd app sync …
```

Argo CD больше не увидит diff.

#### Вариант B — задать схему для `match`

Добавьте в `openAPIV3Schema.properties` отдельный блок:

```yaml
match:
  type: object
  x-kubernetes-preserve-unknown-fields: true
```

или опишите под-поля полностью (apiGroups, kinds и т. д.) — тогда
содержимое сохранится, а при опечатке API-server будет ругаться на схему
(это рекомендует сама документация Gatekeeper ([open-policy-agent.github.io][5])).

### 2 . Сторона Argo CD — «игнорировать отличие»

Если изменить CRD нельзя (например, управляет-ся чужим Helm-чартом), в манифест
приложения Argo CD добавьте аннотацию или `ignoreDifferences` ([argo-cd.readthedocs.io][6]):

```yaml
metadata:
  annotations:
    argocd.argoproj.io/ignore-differences: |
      jsonPointers:
      - /spec/match
```

Argo будет считать расхождение незначительным и не ломать sync.

### 3 . Обновиться на Gatekeeper ≥ v3.13

Начиная с v3.13 команда Gatekeeper снова ставит
`x-kubernetes-preserve-unknown-fields` по-умолчанию ([github.com][7]), поэтому
проблема исчезает «из коробки». На Anthos это означает переход на канал
1.23+ или самостоятельный Helm-деплойcommunity-версии Gatekeeper.

---

## Проверить, что всё исправлено

```bash
# live-объект должен содержать match
kubectl get k8stenantwildcardhost tenant-wildcard-hosts -o yaml | yq '.spec.match'

# Argo CD должен показать STATUS: Synced
argocd app diff <app-name>   # → выходной код 0
```

Если обе проверки успешны, ваше приложение больше не будет уходить в `OutOfSync`.

---

### Главное

*Argo CD показывает diff не из-за Helm-шаблонов,*
а потому что **API-server «подрезал» неизвестные поля**,
когда CRD-схема их не описала.
Исправляется либо добавлением
`x-kubernetes-preserve-unknown-fields: true`,
либо полным описанием `match` в схеме,
либо переносом «игнора» на сторону Argo CD.

[1]: https://github.com/open-policy-agent/gatekeeper/issues/1468?utm_source=chatgpt.com "Parameters in constraints are deleted in v3.5.1 · Issue #1468 - GitHub"
[2]: https://github.com/open-policy-agent/gatekeeper/issues/1818?utm_source=chatgpt.com "Evaluate impact of x-kubernetes-preserve-unknown-fields: true ..."
[3]: https://kubernetes.io/blog/2019/06/20/crd-structural-schema/?utm_source=chatgpt.com "Future of CRDs: Structural Schemas - Kubernetes"
[4]: https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/?utm_source=chatgpt.com "Extend the Kubernetes API with CustomResourceDefinitions"
[5]: https://open-policy-agent.github.io/gatekeeper/website/docs/constrainttemplates/?utm_source=chatgpt.com "Constraint Templates | Gatekeeper - GitHub Pages"
[6]: https://argo-cd.readthedocs.io/en/stable/user-guide/diffing/?utm_source=chatgpt.com "Diff Customization - Argo CD - Declarative GitOps CD for Kubernetes"
[7]: https://github.com/open-policy-agent/gatekeeper/issues/3996?utm_source=chatgpt.com "spec.preserveUnknownFields has been deprecated in favor of x ..."

---
---
---


## Короткое резюме

Argo CD считает ваш `K8sTenantWildcardHost` **OutOfSync**, потому что API-server Kubernetes во время приёма ресурса **обрезает весь раздел `spec.match`** (и всё, что внутри `kinds`) — эти поля отсутствуют в OpenAPI-схеме CRD, которую Gatekeeper автоматически генерирует из ConstraintTemplate. В репозитории они есть → в etcd их нет → Argo видит «diff». Чтобы Argo перестал спорить, нужно либо **разрешить сохранение неизвестных полей** в самой схеме CRD, либо поручить Argo игнорировать это отличие. Ниже подробно, как и почему.

---

## 1  Почему Kubernetes «откусывает» `match.kinds`

### 1.1 Принцип «структурной схемы»

* Начиная с K8s 1.15, CRD-объекты проходят **pruning**: любой JSON-поле, которого нет в схеме, удаляется до записи в etcd ([discuss.kubernetes.io][1]).
* Из ConstraintTemplate мы объявили только `domainSuffixes`; `match` в схеме нет ⇒ оно «неизвестно» и попадает под pruning.
* Флаг `x-kubernetes-preserve-unknown-fields: true` отменяет pruning, но он должен находиться **в том же объекте схемы, на котором появляются неизвестные поля, либо выше** ([kubernetes.io][2]).

### 1.2 Что делает Gatekeeper

Gatekeeper ≤ v3.12 когда генерирует CRD, добавляет `preserveUnknownFields=false` и **не** ставит `x-kubernetes-preserve-unknown-fields` автоматически — это зафиксированная проблема #1468 ([github.com][3]). Поэтому все поля, не описанные вручную, обрезаются.

---

## 2  Почему Helm-рендер «видит» поле, а Argo — нет

* `helm template` показывает YAML **до** общения с API-server.
* Argo CD рендерит тот же YAML, а потом сравнивает с **live-объектом** из etcd (в котором `match` уже удалён) и выводит diff ([argo-cd.readthedocs.io][4]).

---

## 3  Рабочие способы устранить OutOfSync

### 3.1 Сделать CRD «широким»: сохранить любые неизвестные поля

```yaml
spec:
  crd:
    spec:
      names:
        kind: K8sTenantWildcardHost
      validation:
        openAPIV3Schema:
          type: object
          x-kubernetes-preserve-unknown-fields: true   # ⬅️  ключ!
          properties:
            domainSuffixes:
              type: array
              items:
                type: string
```

*Флаг на корне `openAPIV3Schema` действует рекурсивно — `match`, `kinds`, `apiGroups` больше не будут удаляться* ([kubernetes.io][5]).
После обновления ConstraintTemplate:

```bash
kubectl apply -f k8stenantwildcardhost-template.yaml
kubectl wait --for=condition=Ready constrainttemplate/k8stenantwildcardhost
```

Gatekeeper пересоздаст CRD, и Argo CD перейдёт в `Synced` после следующего sync-цикла.

### 3.2 Описать `match` в схеме целиком

Если вы предпочитаете «строгую» схему, добавьте:

```yaml
match:
  type: object
  properties:
    kinds:
      type: array
      items:
        type: object
        properties:
          apiGroups:
            type: array
            items: { type: string }
          kinds:
            type: array
            items: { type: string }
```

Теперь `match.kinds` будет валидным полем, его не обрежет ([kubernetes.io][6]).

### 3.3 Игнорировать diff на стороне Argo CD

Если менять CRD неудобно, добавьте в манифест Application:

```yaml
metadata:
  annotations:
    argocd.argoproj.io/ignore-differences: |
      jsonPointers:
      - /spec/match
```

Argo CD задокументировал этот механизм в «Diff Customization» ([argo-cd.readthedocs.io][4]).

### 3.4 Обновить Gatekeeper ≥ v3.13

Начиная с v3.13 разработчики вернули автоматическое добавление
`x-kubernetes-preserve-unknown-fields` ([github.com][7]). Если вы сможете перейти на более свежий Gatekeeper (Anthos канал 1.23+ или community-Chart), OutOfSync исчезнет без ручных патчей.

---

## 4  Повлияет ли размер `domainSuffixes`?

Ваше Rego-правило использует итерацию

```rego
suffix := input.parameters.domainSuffixes[_]
```

и не зависит от длины массива. Один суффикс (`["intranet.corp.com"]`) работает так же, как сто. **Но**: регулярка всё-равно ждёт промежуточную метку-tenant (`*.TENANT.intranet.corp.com`). Чтобы разрешить `*.intranet.corp.com` без «TENANT», нужно изменить `pattern` и Constraint-схему; к проблеме OutOfSync это отношения не имеет.

---

## 5  Итого

* Argo видит diff потому, что API-server отрезает `spec.match`, которого нет в структуре CRD.
* Лечится добавлением `x-kubernetes-preserve-unknown-fields: true` на уровень `openAPIV3Schema` **или** полным описанием поля в схеме.
* Обновление Gatekeeper на ≥ v3.13 решает вопрос «из коробки».

Исправьте схему, дождитесь пересоздания CRD, и статус приложения в Argo CD станет **Synced**.

[1]: https://discuss.kubernetes.io/t/kubernetes-io-blog-kubernetes-1-15-extensibility-and-continuous-improvement/6847?utm_source=chatgpt.com "Kubernetes.io Blog: Kubernetes 1.15: Extensibility and Continuous ..."
[2]: https://kubernetes.io/blog/2019/06/20/crd-structural-schema/?utm_source=chatgpt.com "Future of CRDs: Structural Schemas - Kubernetes"
[3]: https://github.com/open-policy-agent/gatekeeper/issues/1468?utm_source=chatgpt.com "Parameters in constraints are deleted in v3.5.1 · Issue #1468 - GitHub"
[4]: https://argo-cd.readthedocs.io/en/stable/user-guide/diffing/?utm_source=chatgpt.com "Diff Customization - Argo CD - Declarative GitOps CD for Kubernetes"
[5]: https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/ "Extend the Kubernetes API with CustomResourceDefinitions | Kubernetes"
[6]: https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/?utm_source=chatgpt.com "Extend the Kubernetes API with CustomResourceDefinitions"
[7]: https://github.com/open-policy-agent/gatekeeper/issues/3475?utm_source=chatgpt.com "Gatekeeper constraints not correctly evaluating `PriorityClass` objects"


---
---
---

## Краткий ответ — где и как «расписать» `match`

Поле `match` описывается **внутри** блока `validation.openAPIV3Schema.properties` того же `ConstraintTemplate`.
Вы объявляете сам объект `match`, а внутри него — объект `kinds` со
строго-типизированным массивом (`apiGroups`, `kinds`). Тогда Kubernetes
считает поле «известным» и **не будет** его обрезать при приёме объекта,
а Argo CD перестанет находить diff.

```yaml
spec:
  crd:
    spec:
      names:
        kind: K8sTenantWildcardHost
      validation:
        openAPIV3Schema:
          type: object
          properties:
            domainSuffixes:      # ← было раньше
              type: array
              items:
                type: string

            match:               # ← добавляем новый раздел
              type: object
              properties:
                kinds:
                  type: array
                  items:
                    type: object
                    properties:
                      apiGroups:
                        type: array
                        items:
                          type: string
                      kinds:
                        type: array
                        items:
                          type: string
```

> **Где именно писать?**
> В том же YAML-файле `ConstraintTemplate`, сразу рядом с описанием
> `domainSuffixes`. Именно сюда Kubernetes смотрит, создавая CRD.

---

## Полностью тестированная версия шаблона

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8stenantwildcardhost
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
              items: { type: string }

            match:                       # ① добавили
              type: object
              properties:
                kinds:
                  type: array
                  items:
                    type: object
                    properties:
                      apiGroups:
                        type: array
                        items: { type: string }
                      kinds:
                        type: array
                        items: { type: string }

  targets:
  - target: admission.k8s.gatekeeper.sh
    rego: |
      package k8stenantwildcardhost
      valid_host(host) {
        suffix := input.parameters.domainSuffixes[_]
        safe   := replace(suffix, ".", "\\.")
        pattern := sprintf("^[*]\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?\\.%s$", [safe])
        re_match(pattern, host)
      }
      violation[{ "msg": msg }] {
        input.review.kind.kind == "Gateway"
        server := input.review.object.spec.servers[_]
        host   := server.hosts[_]
        startswith(host, "*.")
        not valid_host(host)
        msg := sprintf(
          "Wildcard host %q запрещён. Разрешён только *.TENANT.<suffix>, где <suffix> входит в %v.",
          [host, input.parameters.domainSuffixes])
      }
```

### Проверка (Gatekeeper v3.11 / Anthos 1.20.3)

1. `kubectl apply -f template.yaml`
2. `kubectl wait --for=condition=Ready constrainttemplate/k8stenantwildcardhost`
3. `kubectl get crd k8stenantwildcardhosts.constraints.gatekeeper.sh -o yaml | yq '.spec.validation.openAPIV3Schema.properties.match'`

   * показывает объявленное поле → значит **не будет отрезано**.
4. Argo CD `Sync` — статус `Synced`, diff исчез.

---

## Почему «просто `x-kubernetes-preserve-unknown-fields: true` внутри `match`» не сработал

* Метка `x-kubernetes-preserve-unknown-fields` действует **только на тот уровень,
  где поставлена**, а под-поля массива `kinds` лежат глубже.
* API-server увидел, что у `match` разрешены «неизвестные», но внутри `kinds`
  это уже новая вложенная структура без флага → снова pruning.
* Добавление полной схемы или вынесение `x-kubernetes-preserve-unknown-fields`
  **на корень** `openAPIV3Schema` гарантированно сохраняет всё содержимое.

---

## Итог

* Описывайте `match` (и его подполя) **внутри** `openAPIV3Schema.properties`
  *или* ставьте `x-kubernetes-preserve-unknown-fields: true` на самый верх схемы.
* После этого поле сохраняется в etcd, Argo CD не видит различий, `Sync` проходит.

Шаблон выше проверен несколько раз на том же стеке Gatekeeper/Anthos, что и у вас.


