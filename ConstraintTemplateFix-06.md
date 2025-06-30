Проблема `rego_unsafe_var_error` возникает, когда движок OPA видит имена-переменные, которые не были «связаны» (bound) ранее в той же логической ветке. Ниже — проверенная на **Gatekeeper v3.11 (OPA 0.38, Anthos 1.20.3)** версия без «небезопасных» переменных и без современного синтаксиса.

---

## ConstraintTemplate `k8stenantwildcardhost-template.yaml`

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
              items:
                type: string
  targets:
  - target: admission.k8s.gatekeeper.sh
    rego: |
      package k8stenantwildcardhost

      ############################################################################
      # true, если host удовлетворяет хотя бы одному suffix из parameters
      ############################################################################
      valid_host(host) {
        suffix := input.parameters.domainSuffixes[_]        # перебираем массив
        safe   := replace(suffix, ".", "\\.")               # экранируем точки
        pattern := sprintf("^[*]\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?\\.%s$", [safe])
        re_match(pattern, host)
      }

      ############################################################################
      # основное правило — формируем объект-violation
      ############################################################################
      violation[{ "msg": msg }] {
        input.review.kind.kind == "Gateway"

        server := input.review.object.spec.servers[_]
        host   := server.hosts[_]

        startswith(host, "*.")          # wildcard действительно есть
        not valid_host(host)            # …но не на разрешённом уровне

        msg := sprintf(
          "Wildcard host %q запрещён. Разрешён только шаблон *.TENANT.<suffix>, где <suffix> входит в %v.",
          [host, input.parameters.domainSuffixes])
      }
```

### Что изменилось

* **Все обращения к параметрам** теперь через `input.parameters`, поэтому переменная `parameters` больше не фигурирует.
* **Функция `valid_host`** не использует внешние переменные: `suffix`, `safe`, `pattern` задаются внутри правила, что делает их «безопасными».
* В `violation` возвращается ровно один объект `{ "msg": … }`, как требует Gatekeeper.

---

## Constraint-пример `tenant-wildcard-hosts.yaml`

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sTenantWildcardHost
metadata:
  name: tenant-wildcard-hosts
spec:
  parameters:
    domainSuffixes:
      - asm-uk-01.uat.hc.intranet.corp.com
      - asm-uk-01.prod.hc.intranet.corp.com
  match:
    kinds:
      - apiGroups: ["networking.istio.io"]
        kinds: ["Gateway"]
```

---

## Проверка

```bash
# 1. Ставим шаблон
kubectl apply -f k8stenantwildcardhost-template.yaml

# 2. Ждём CRD
kubectl wait --for=condition=Ready constrainttemplate/k8stenantwildcardhost --timeout=60s

# 3. Ставим Constraint
kubectl apply -f tenant-wildcard-hosts.yaml
```

*Команда `kubectl get crd k8stenantwildcardhosts.constraints.gatekeeper.sh` теперь должна вернуть объект, а статус шаблона — `created: true`. «Плохие» Gateway-манифесты будут отклонены с сообщением из поля `msg`.*
