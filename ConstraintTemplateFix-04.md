Ниже приведены **полные, рабочие** манифесты YAML для:

1. **ConstraintTemplate** `k8stenantwildcardhost` (совместим с Gatekeeper v3.11 / Anthos 1.20.3).
2. Пример **Constraint** `K8sTenantWildcardHost`, использующий этот шаблон.

---

### 1. ConstraintTemplate — `k8stenantwildcardhost-template.yaml`

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8stenantwildcardhost
  annotations:
    description: |
      Blocks overly-broad wildcards in Istio Gateway .spec.servers[*].hosts.
      Разрешён только вид:  *.TENANT.<domainSuffix>
      TENANT — любая RFC-1123 DNS-метка.
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
                One or more fixed DNS suffixes that must follow the tenant label,
                e.g. "asm-uk-01.uat.hc.intranet.corp.com".
              items:
                type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8stenantwildcardhost

        ############################################################################
        # helper: returns true if host matches *.<tenant>.<any allowed suffix>
        ############################################################################
        allowed(host) {
          suffixes := parameters.domainSuffixes
          suff := suffixes[_]                       # перебираем массив «по-старому»
          safe := replace(suff, ".", "\\.")         # экранируем точки
          pat  := sprintf("^[*]\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?\\.%s$", [safe])
          re_match(pat, host)
        }

        ############################################################################
        # main rule: raise violation on forbidden wildcard hosts
        ############################################################################
        violation[msg] {
          input.review.kind.kind == "Gateway"

          server := input.review.object.spec.servers[_]
          host   := server.hosts[_]

          startswith(host, "*.")        # wildcard действительно используется
          not allowed(host)             # но расположен выше разрешённого уровня

          msg := sprintf(
            "Wildcard host %q запрещён. Допустимы только шаблоны вида *.TENANT.<%v>.",
            [host, parameters.domainSuffixes])
        }
```

---

### 2. Constraint — `tenant-wildcard-hosts.yaml`

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

> **Порядок применения**

```bash
# 1. Устанавливаем шаблон
kubectl apply -f k8stenantwildcardhost-template.yaml

# 2. Дожидаемся готовности (важно!)
kubectl wait --for=condition=Ready constrainttemplate/k8stenantwildcardhost --timeout=60s

# 3. Создаём Constraint
kubectl apply -f tenant-wildcard-hosts.yaml
```

После этого Gatekeeper начнёт отклонять любые Istio Gateway, где `hosts`
используют `*.` выше уровня `<TENANT>.<domainSuffix>`.
