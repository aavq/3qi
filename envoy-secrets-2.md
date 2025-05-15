Below is a step-by-step, production-ready guide to configuring Envoy’s **OAuth2 HTTP filter** in an Istio service-mesh.  It shows two placement strategies—**`SIDECAR_INBOUND`** and **`GATEWAY`**—and walks through building, validating, and publishing the required `Secret` objects (HMAC and token) in Kubernetes and Google Secret Manager (GSM).  All commands are safe to paste into a shell; adapt namespaces, project IDs, and secret names to your environment.

---

## 1  Choose where the filter runs

| Context               | Traffic protected                                            | Where the secrets live                      | Typical use case             |
| --------------------- | ------------------------------------------------------------ | ------------------------------------------- | ---------------------------- |
| **`SIDECAR_INBOUND`** | Only inbound traffic to one workload                         | The workload’s own namespace                | Per-service login pages      |
| **`GATEWAY`**         | All traffic that enters the mesh through the ingress gateway | `istio-system` (or the gateway’s namespace) | Centralised auth at the edge |

Istio applies the `context` field of an `EnvoyFilter` at compile time; use `SIDECAR_INBOUND` for sidecars and `GATEWAY` for gateways.([Istio][1])

---

## 2  Generate strong secrets

```bash
python3 - <<'PY'
import secrets, textwrap, os
hmac = secrets.token_hex(32)          # 256-bit HMAC key
token = secrets.token_urlsafe(24)     # random token symmetric key
print("HMAC =", hmac)
print("TOKEN =", token)
PY
```

The Python `secrets` module provides cryptographically secure randomness and is the preferred way to generate keys.([Python documentation][2])
Record both values in a password manager; they are never committed to source control.

---

## 3  Create Envoy SDS secret files

Create **`hmac.yaml`**:

```yaml
---
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: hmac
  generic_secret:
    secret:
      inline_string: <32-byte-hex-string>
```

Create **`token-secret.yaml`**:

```yaml
---
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: token
  generic_secret:
    secret:
      inline_string: <random-token>
```

`generic_secret` objects are served to Envoy via the **Secret Discovery Service (SDS)** and can be rotated without restarting the proxy.([Envoy Proxy][3])

---

## 4  Bundle the files into JSON for GSM

```bash
jq -n --rawfile h hmac.yaml --rawfile t token-secret.yaml \
   '{ "hmac.yaml": $h, "token-secret.yaml": $t }' \
   > oauth-secrets.json
```

`jq --rawfile` reads each YAML file as a string and embeds it verbatim, preserving new-lines.([Stack Overflow][4])

### Optional: Local validation

```bash
jq -r '."hmac.yaml"' oauth-secrets.json | istioctl validate -f -
```

`istioctl validate` parses Envoy/UDPA resources and catches schema errors before you push them to production.([GitHub][5])

---

## 5  Publish the bundle to Google Secret Manager

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>

# Ensure the secret exists (create it once):
# gcloud secrets create ingress-gateway-oauth-secrets --replication-policy="automatic"

gcloud secrets versions add ingress-gateway-oauth-secrets \
      --data-file=oauth-secrets.json
```

`gcloud secrets versions add` uploads a new immutable version; Envoy can later load it via Workload Identity.([Google Cloud][6]) ([Google Cloud][7])

---

## 6  Create the Kubernetes Secret (if not using GSM mount-points)

```bash
kubectl -n istio-system create secret generic ingress-gateway-oauth-secrets \
  --from-file=hmac.yaml \
  --from-file=token-secret.yaml
```

Kubernetes `Opaque` secrets store base-64 strings and are automatically mounted into the gateway pods when referenced.([Kubernetes][8])

---

## 7  Attach the OAuth2 filter

### Gateway example (`context: GATEWAY`)

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: ingress-oauth2
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
          token_endpoint:
            uri: https://oauth.example.com/token
            cluster: oauth
            timeout: 3s
          authorization_endpoint: https://oauth.example.com/authorize
          redirect_uri: "%REQ(X-Forwarded-Proto)%://%REQ(:authority)%/callback"
          redirect_path_matcher:
            path:
              exact: /callback
          credentials:
            client_id: my-client
            token_secret:
              name: token
              sds_config: { path: "/etc/envoy/token-secret.yaml" }
            hmac_secret:
              name: hmac
              sds_config: { path: "/etc/envoy/hmac.yaml" }
          forward_bearer_token: true
```

The filter’s full schema is documented in Envoy’s reference.([Envoy Proxy][9]) A working end-to-end sample is available on GitHub.([GitHub][10])

### Sidecar example (`context: SIDECAR_INBOUND`)

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: reviews-oauth2
  namespace: reviews
spec:
  workloadSelector:
    labels:
      app: reviews
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: SIDECAR_INBOUND
      listener:
        filterChain:
          filter:
            name: envoy.filters.network.http_connection_manager
    patch:
      operation: INSERT_BEFORE
      value:
        # (same OAuth2 configuration as above)
```

For sidecars, place the HMAC/token `Secret` in the same namespace as the workload so that Istio’s SDS agent can mount it automatically.([Istio][1])

---

## 8  Verify the deployment

```bash
# 1. Check the gateway loads the secrets
kubectl -n istio-system logs deploy/istio-ingressgateway \
        -c istio-proxy | grep oauth2

# 2. Watch Envoy config on the pod
istioctl proxy-config listener <POD> -n istio-system

# 3. Exercise the flow
curl -k https://<GATEWAY_HOST>/anything
```

If the filter is active, the request is **302**-redirected to the IdP’s `authorization_endpoint`; once the callback returns, cookies named `OauthHMAC` and `BearerToken` appear.([Envoy Proxy][9])

---

## 9  Operational best practices

* **Rotate secrets** regularly; SDS lets you add a new GSM version and Envoy will pick it up without restart.([Envoy Proxy][11])
* **Limit scope** by creating distinct HMAC/token pairs per environment (dev/stage/prod).
* **Enforce mTLS** on the gateway to keep tokens encrypted on the wire.([Istio][12])
* **Audit access** with IAM: grant `roles/secretmanager.secretAccessor` only to the service account that runs the gateway.([Google Cloud][7])

---

### Further reading

* Envoy OAuth2 design doc –  deep dive into the filter’s cookies and flows([Envoy Proxy][9])
* Istio EnvoyFilter cookbook for advanced patterns([GitHub][13])
* End-to-end demo with OIDC and HMAC validation([GitHub][10])

With these steps, you have a repeatable, secure pipeline for adding OAuth2 authentication—either edge-wide or per-service—into any Istio-managed Kubernetes cluster.

[1]: https://istio.io/latest/docs/reference/config/networking/envoy-filter/?utm_source=chatgpt.com "Envoy Filter - Istio"
[2]: https://docs.python.org/3/library/secrets.html?utm_source=chatgpt.com "secrets — Generate secure random numbers for managing secrets ..."
[3]: https://www.envoyproxy.io/docs/envoy/latest/configuration/security/secret?utm_source=chatgpt.com "Secret discovery service (SDS) - Envoy proxy"
[4]: https://stackoverflow.com/questions/67596741/how-to-combine-two-json-variables-using-jq?utm_source=chatgpt.com "how to combine two json variables using jq - Stack Overflow"
[5]: https://github.com/istio/istio/wiki/EnvoyFilter-Samples?utm_source=chatgpt.com "EnvoyFilter Samples · istio/istio Wiki - GitHub"
[6]: https://cloud.google.com/sdk/gcloud/reference/secrets/versions/add?utm_source=chatgpt.com "gcloud secrets versions add | Google Cloud CLI Documentation"
[7]: https://cloud.google.com/secret-manager/docs/add-secret-version "Add a secret version  |  Secret Manager Documentation  |  Google Cloud"
[8]: https://kubernetes.io/docs/concepts/configuration/secret/?utm_source=chatgpt.com "Secrets | Kubernetes"
[9]: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/oauth2_filter?utm_source=chatgpt.com "OAuth2 — envoy 1.35.0-dev-f2a1a6 documentation"
[10]: https://github.com/salrashid123/envoy_oauth2 "GitHub - salrashid123/envoy_oauth2: Envoy Oauth2 Filter helloworld"
[11]: https://www.envoyproxy.io/docs/envoy/latest/configuration/security/secret "Secret discovery service (SDS) — envoy 1.35.0-dev-2b9efa documentation"
[12]: https://istio.io/latest/docs/ambient/usage/verify-mtls-enabled/?utm_source=chatgpt.com "Verify mutual TLS is enabled - Istio"
[13]: https://github.com/istio/istio/wiki/EnvoyFilter-Samples "EnvoyFilter Samples · istio/istio Wiki · GitHub"
