Below is a **ready-to-paste Markdown Subsystem Design Document (SSD)** that shows how to introduce the **`envoy.filters.http.oauth2`** HTTP-filter into an existing Istio ingress-gateway so that every browser request is transparently authenticated against an external Cloud Identity Provider (IdP).  The template keeps the structure we discussed earlier and is already filled with Istio-specific recommendations, example YAML fragments, and a **Mermaid sequence diagram** of the full Authorization-Code + PKCE flow.

---

## Why these choices (high-level)

* Istio places Envoy sidecars in the *data plane* while istiod drives configuration from the *control plane* ([istio.io][1]).
* Envoy natively ships the OAuth2 HTTP filter; Istio exposes it through the `EnvoyFilter` CRD or a `WasmPlugin` ([envoyproxy.io][2], [istio.io][3], [istio.io][4]).
* The recommended pattern is *Authorization-Code + PKCE* because it is universally supported by IdPs and avoids the weaknesses of legacy ROPC/implicit flows ([oauth.net][5], [oauth.net][6]).
* Real-world tutorials (Okta, Keycloak) and field reports (J.P. Morgan) prove the pattern works at scale and highlight common pitfalls ([gist.github.com][7], [medium.com][8], [devforum.okta.com][9], [jpmorgan.com][10]).

Copy the code block into `SUBSYSTEM_DESIGN.md`, replace the `{{…}}` placeholders with values from your environment (cluster domain, client ID/secret, IdP endpoints), and commit it to Git so that reviewers can comment via pull-request.

---

````markdown
# Subsystem Design Document (SSD): Istio OAuth2 Extension
<!-- Replace {{…}} placeholders and remove helper comments as you fill it in -->

## 1 · Overview & Context
### 1.1 Purpose
The **OAuth2 Extension** enables browser-based users to authenticate through an external Cloud IdP (e.g., Azure AD, Okta) before any HTTP request enters the service mesh.  The feature is implemented by injecting the native **envoy.filters.http.oauth2** filter into the Istio IngressGateway.  It targets p99 < 350 ms added latency at ≤ 5 000 RPS.

### 1.2 Scope & Boundaries
| Item                     | In Scope                                | Out of Scope |
|--------------------------|-----------------------------------------|--------------|
| Authentication           | OAuth2 Authorization-Code + PKCE flow   | SAML, OIDC Hybrid |
| Workloads affected       | ingress-gateway & web UI workloads      | gRPC internal services |
| Resilience objective     | Gateway Availability ≥ 99.95 %          | IdP SLA |

> **Business impact** – Without the extension, public web UIs run unauthenticated, breaching corporate security baseline.

---

## 2 · Responsibilities & Boundaries
* **Single Responsibility:** enforce user auth **before** traffic reaches any upstream HTTP service.  
* **Upstream dependencies:** external IdP reachable over HTTPS (:443).  
* **Downstream dependencies:** internal services expect a valid `Authorization: Bearer` header or `BearerToken` cookie.

```mermaid
flowchart LR
  A[Browser] -- 1. Request /app --> B[Istio IngressGateway\n(Envoy + OAuth2)]
  B -- 2. 302 Redirect to IdP --> C[[Cloud IdP\nAuthorize Endpoint]]
  C -- 3. Login & Consent --> C
  C -- 4. 302 code+state --> B
  B -- 5. POST code ➜ token_endpoint --> D[[Cloud IdP\nToken Endpoint]]
  D -- 6. access_token, id_token --> B
  B -- 7. Set-Cookie BearerToken\n/ Add Authorization header --> E[Upstream Service]
  E -- 8. 200 OK --> A
````

---

## 3 · Interface Contracts (ICD)

| Element                | Value / Example                                      |
| ---------------------- | ---------------------------------------------------- |
| **Authorization URL**  | `https://login.exampleidp.com/oauth2/v2.0/authorize` |
| **Token URL**          | `https://login.exampleidp.com/oauth2/v2.0/token`     |
| **Client ID / Secret** | Stored in K8s `Secret` (`istio-system/oauth2-creds`) |
| **Redirect URI**       | `https://{{gateway_fqdn}}/oauth2/callback`           |

* **Idempotency:** The Envoy filter enforces the `state` parameter and one-time `code` usage.
* **Versioning:** API v1; breaking changes will be shipped under `/v2/*`.
* **SLA:** Token exchange ≤ 500 ms (p95).

---

## 4 · Internal Architecture

### 4.1 Component Diagram (C4 – level 3)

```mermaid
graph TD
  subgraph IngressGateway Pod
    P1[Envoy\nHTTP Connection Manager]
    P2[Envoy OAuth2 Filter]
    P3[Envoy Router]
  end
  subgraph Control Plane
    I[istiod]
    C[K8s API Server]
  end
  P1 --> P2 --> P3 --> Upstream
  I <--> C
  I ==> P1
```

### 4.2 Configuration Snippet (EnvoyFilter)

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: oauth2-filter
  namespace: istio-system
spec:
  workloadSelector:
    labels:
      istio: ingressgateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
      listener:
        filterChain:
          filter:
            name: envoy.filters.network.http_connection_manager
    patch:
      operation: INSERT_BEFORE
      value:
        name: envoy.filters.http.oauth2
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
          config:
            token_endpoint: "https://login.exampleidp.com/oauth2/v2.0/token"
            authorization_endpoint: "https://login.exampleidp.com/oauth2/v2.0/authorize"
            redirect_uri: "https://{{gateway_fqdn}}/oauth2/callback"
            credentials:
              client_id: "{{CLIENT_ID}}"
              token_secret:
                name: oauth2-creds
                key: client_secret
```

---

## 5 · Architectural Decisions (ADR Log)

| ID  | Decision                                           | Status   | Date       |
| --- | -------------------------------------------------- | -------- | ---------- |
| 014 | Use Envoy native OAuth2 filter vs external sidecar | Accepted | 2025-05-28 |
| 015 | Enforce PKCE for browser flows                     | Accepted | 2025-05-30 |

(see `/docs/adr/014-use-envoy-oauth2.md` for context and trade-offs)

---

## 6 · Non-Functional Requirements (NFR)

| Attribute           | Target                 | Rationale                  |
| ------------------- | ---------------------- | -------------------------- |
| Availability        | ≥ 99.95 %              | Tier-0 web entrypoint      |
| Added latency (p99) | ≤ 350 ms               | UX budget                  |
| Throughput          | 5 000 RPS              | 2× 12-month growth         |
| Error budget        | 0.1 % unauth redirects | Align with SRE latency SLO |

---

## 7 · Security & Threat Model

1. **STRIDE** on components identifies *Spoofing* at callback and *Information disclosure* in tokens.
2. Counter-measures: HSTS, SameSite cookies, short-lived (15 min) access-tokens, encrypted K8s secrets.
3. Compliance: Follows OWASP ASVS 4.0, PCI-DSS section 8 for auth.

---

## 8 · Operations & Observability

* **CI/CD:** GitHub → Tekton → Istio Canary (5 %) with auto-rollback on 5xx > 1 %.
* **Metrics exported by filter:** `oauth2_total_redirects`, `oauth2_token_failures`.
* **Dashboards:** Grafana board `Istio-OAuth2.json`.
* **Alerts:** > 0.5 % token failures (5 m) triggers PagerDuty P2.

---

## 9 · Constraints & Risks

| Risk                     | Impact              | Mitigation                                     |
| ------------------------ | ------------------- | ---------------------------------------------- |
| IdP latency spikes       | User-visible delays | Circuit-breaker, 2 s timeout                   |
| IdP certificate rotation | Outage              | Monitor `x509_expiry` metric, renew via GitOps |

---

## 10 · Roadmap & Evolution

* **v1 (2025-Q3):** OAuth2 on ingress-gateway only.
* **v2 (2025-Q4):** Move auth to per-sidecar with `WasmPlugin` for mTLS internal calls.
* **Deprecation:** `v1` stays 6 mo after `v2` GA.

---

## Appendix

* **Glossary:** PKCE, IdP, EnvoyFilter, WasmPlugin.
* **References:** ADRs 014-015, Envoy OAuth2 docs, Istio EnvoyFilter docs.

```

---

### Source highlights

* Istio splits data/control planes and configures sidecar proxies via Envoy :contentReference[oaicite:4]{index=4}.  
* The `envoy.filters.http.oauth2` filter and its redirect/token logic are documented in Envoy upstream :contentReference[oaicite:5]{index=5}.  
* Istio exposes native filters through the `EnvoyFilter` CRD :contentReference[oaicite:6]{index=6} or via `WasmPlugin` for Wasm-based extensions :contentReference[oaicite:7]{index=7}.  
* Authorization-Code + PKCE is the recommended browser flow per OAuth 2.0 core and RFC 7636 :contentReference[oaicite:8]{index=8}.  
* Community examples show Okta :contentReference[oaicite:9]{index=9}, Keycloak :contentReference[oaicite:10]{index=10} and troubleshooting tips from Okta/Envoy users :contentReference[oaicite:11]{index=11}.  
* Field experience from JPMorgan confirms redirect patterns and header propagation :contentReference[oaicite:12]{index=12}.  
* The Envoy proto spec details every configurable field (client_id, redirect_uri, scopes) :contentReference[oaicite:13]{index=13}.  
* Istio’s `CUSTOM` authz action can delegate to external services if you later need fine-grained RBAC :contentReference[oaicite:14]{index=14}.  
* PKCE strengthens the flow against interception and CSRF :contentReference[oaicite:15]{index=15}.  
* Microsoft’s docs illustrate alternate ROPC flow and why we avoid it here :contentReference[oaicite:16]{index=16}.  
* GitHub issue 56169 warns that `WasmPlugin` currently attaches only to sidecars, not gateways – plan for Istio 1.23 fix :contentReference[oaicite:17]{index=17}.

Use the template as a *living* document: every time you change the filter config, bump the ADR and commit the SSD so that architecture, code, and operations stay in lock-step.
::contentReference[oaicite:18]{index=18}
```

[1]: https://istio.io/latest/docs/ops/deployment/architecture/?utm_source=chatgpt.com "Istio / Architecture"
[2]: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/oauth2_filter?utm_source=chatgpt.com "OAuth2 — envoy 1.35.0-dev-e10f06 documentation"
[3]: https://istio.io/latest/docs/reference/config/networking/envoy-filter/?utm_source=chatgpt.com "Envoy Filter - Istio"
[4]: https://istio.io/latest/docs/reference/config/proxy_extensions/wasm-plugin/?utm_source=chatgpt.com "Wasm Plugin - Istio"
[5]: https://oauth.net/2/grant-types/authorization-code/?utm_source=chatgpt.com "OAuth 2.0 Authorization Code Grant Type"
[6]: https://oauth.net/2/pkce/?utm_source=chatgpt.com "PKCE for OAuth 2.0"
[7]: https://gist.github.com/jdgomeza/9cb11fedffb09924ed410c666cc06ad1?utm_source=chatgpt.com "Istio OAuth2 Envoy Filter (Okta example) - GitHub Gist"
[8]: https://medium.com/%40senthilrch/api-authentication-using-istio-ingress-gateway-oauth2-proxy-and-keycloak-part-2-of-2-dbb3fb9cd0d0?utm_source=chatgpt.com "API Authentication: Configure Istio IngressGateway, OAuth2-Proxy ..."
[9]: https://devforum.okta.com/t/istio-envoy-oauth2-filter-configuration/20552?utm_source=chatgpt.com "Istio Envoy OAuth2 Filter Configuration - Okta Developer Community"
[10]: https://www.jpmorgan.com/technology/technology-blog/protecting-web-applications-via-envoy-oauth2-filter?utm_source=chatgpt.com "Protecting web applications via Envoy OAuth2 filter - J.P. Morgan"
