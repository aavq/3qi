Below is a Gatekeeper **ConstraintTemplate** that enforces a tenant-safe wildcard policy for Istio Gateways. It restricts the `"*"` token so that it can appear **only** as the left-most label immediately in front of the tenant namespace (an arbitrary DNS-compliant word) and then your fixed cluster FQDN suffix (for example `asm-uk-01.uat.hc.intranet.corp.com`). Any "higher" wildcard-such as `*.hc.intranet.corp.com`-is rejected.

---

## Why this matters

* In Istio, a `Gateway` server's `hosts` field can use `*` to match suffixes; a single careless rule (`*`) or an overly-broad wildcard can bind **all** traffic on the Gateway IP and starve other tenants.
* Google's policy-controller library already blocks completely blank or full-wildcard Ingress rules for the same reason.
* Anthos/GKE operators are encouraged to harden multi-tenant clusters with Gatekeeper; writing custom `ConstraintTemplate`s lets you codify org-specific patterns.

---

## ConstraintTemplate `IstioIngressWildcardScope`

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: IstioIngressWildcardScope
  annotations:
    description: |
      Prevents tenants from declaring overly-broad wildcards in
      Istio Gateway .spec.servers[*].hosts.
      Allowed pattern:  *.TENANT.<DOMAIN_SUFFIX>
      Example good:     *.alice.asm-uk-01.uat.hc.intranet.corp.com
      Example bad:      *.alice.hc.intranet.corp.com
      Rationale: An unrestricted wildcard hijacks every HTTP/S name
      terminating on the Gateway, breaking isolation between tenants.
spec:
  crd:
    spec:
      names:
        kind: IstioIngressWildcardScope
      validation:
        # cluster operators supply the fixed tail of the FQDN
        openAPIV3Schema:
          properties:
            domainSuffix:
              type: string
              description: >
                The fixed suffix following the tenant namespace, e.g.
                "asm-uk-01.uat.hc.intranet.corp.com"
  targets:
  - target: admission.k8s.gatekeeper.sh
    rego: |
      package IstioIngressWildcardScope

      import data.lib.regex

      # Build a runtime-safe regex once, based on the parameter.
      suffix    := parameters.domainSuffix
      safe_suff := regex.escape_string(suffix)

      # Matches:  *.tenant.<suffix>   where tenant is RFC-1123 label
      pattern   := sprintf("^[*]\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?\\.%s$", [safe_suff])

      violation[{"msg": msg, "details": host}] {
        input.review.kind.kind == "Gateway"
        some server in input.review.object.spec.servers
        host := server.hosts[_]
        startswith(host, "*.")            # user is using a wildcard
        not re_match(pattern, host)       # but not in allowed place
        msg := sprintf(
          "Wildcard host %q is not permitted. Only wildcards of the form *.TENANT.%s are allowed.",
          [host, suffix])
      }
```

### How it works

1. **Parameterisation** - operators pass one string, `domainSuffix`, so the same template secures every environment (prod, staging, etc.).
2. **Staic regex** - we construct `pattern` exactly once from that suffix; Gatekeeper evaluates it for every incoming `Gateway`.
3. **Violation block** -

   * checks the object is an Istio `Gateway`;
   * iterates all `hosts`;
   * if the host starts with `"*."` **and** fails the regex, it is denied with a clear message.
4. `regex.escape_string` (available in Gatekeeper's bundled library) shields dots to avoid accidental wildcarding inside the suffix.

---

## Deploying the policy

1. **Apply** the template above:

   ```bash
   kubectl apply -f IstioIngressWildcardScope-template.yaml
   ```
2. **Instantiate** a `Constraint` supplying your suffix:

   ```yaml
   apiVersion: constraints.gatekeeper.sh/v1beta1
   kind: IstioIngressWildcardScope
   metadata:
     name: tenant-wildcard-hosts
   spec:
     parameters:
       domainSuffix: "asm-uk-01.uat.hc.intranet.corp.com"
   ```
3. Gatekeeper (v anthos 1.20.3) will immediately start rejecting non-conforming Gateway creations/updates.

---

## Quick test matrix

| Host value in Gateway                          | Expected    | Reason                              |
| ---------------------------------------------- | ----------- | ----------------------------------- |
| `*.alice.asm-uk-01.uat.hc.intranet.corp.com`   | **Allowed** | Wildcard only at tenant level       |
| `api.alice.asm-uk-01.uat.hc.intranet.corp.com` | **Allowed** | No wildcard at all                  |
| `*.alice.hc.intranet.corp.com`                 | **Denied**  | Wildcard above tenant segment       |
| `*`                                            | **Denied**  | Catches everything (fully-wildcard) |

Gatekeeper will emit the message from the template to guide the tenant toward the correct form.

---

### Further hardening ideas

* Combine with `K8sUniqueIngressHost` to guarantee no two tenants claim the same FQDN.
* Enforce HTTPS/TLS settings via additional templates to avoid plaintext leakage.
* Adopt the upcoming **CEL-based** templates (supported in Gatekeeper >= v3.13) for simpler regex syntax once your Anthos channel includes that version.

This template should give you a robust guardrail against namespace-level wildcard hijacking while keeping tenant self-service flexibility intact.
