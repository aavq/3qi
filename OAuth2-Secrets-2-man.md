** How to wire Envoy’s built-in *oauth2* filter to Istio in a secure, maintainable way**

1. **Decide where you enforce authentication** (ingress gateway *vs.* workload sidecar).
2. **Generate two credentials — `token` and `hmac` — in Envoy *Secret Discovery Service* (SDS) format.**
3. **Bundle those YAML fragments into a JSON object and upload it as a new version of a Secret in Google Cloud Secret Manager (GSM).**
4. **Synchronise the GSM secret into Kubernetes with External Secrets Operator (ESO).**
5. **Mount the resulting K8s Secret into either the ingress-gateway Deployment or the application Pods (via `sidecar.istio.io/*` annotations).**
6. **Attach an `EnvoyFilter` that inserts the OAuth2 HTTP filter in the selected context (GATEWAY or SIDECAR\_INBOUND).**
   The sections below expand each step, add validation commands and wrap up with production-grade best practices.

---

## 1. Choose the enforcement context

| Context              | When to use                                              | Where the K8s Secret must live                  |
| -------------------- | -------------------------------------------------------- | ----------------------------------------------- |
| **GATEWAY**          | Multi-service mesh entry point; single auth flow         | `istio-system` namespace (ingress gateway pods) |
| **SIDECAR\_INBOUND** | Per-service or per-namespace auth; fine-grained policies | Namespace of the workload that gets the sidecar |

`context: GATEWAY` and `context: SIDECAR_INBOUND` are the canonical match keys in an `EnvoyFilter` patch. ([Istio][1])

---

## 2. Create the credentials in SDS format

### 2.1 Generate secrets

```bash
python3 - <<'PY'
import secrets, textwrap, yaml
print(secrets.token_hex(32))
PY
```

A 32-byte hex string (256 bits) meets Envoy’s *generic\_secret* expectations — one value for `token`, one for `hmac`. ([Envoy Proxy][2])

### 2.2 Author SDS YAML

```yaml
# hmac.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: hmac
  generic_secret:
    secret:
      inline_string: <HMAC_HEX>
```

Repeat for **token-secret.yaml** (name `token`). Both keys are required by the filter. ([Envoy Proxy][2])

### 2.3 Bundle to JSON for GSM

```bash
jq -n --rawfile h hmac.yaml --rawfile t token-secret.yaml \
   '{ "hmac.yaml": $h, "token-secret.yaml": $t }' > oauth-secrets.json
```

---

## 3. Store or rotate the bundle in Google Cloud Secret Manager

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud secrets versions add ENVOY_CRED_BUNDLE \
     --data-file=oauth-secrets.json
```

The `gcloud secrets versions add` command pushes a new immutable version; RBAC roles **Secret Version Adder/Manager** are required. ([Google Cloud][3], [Google Cloud][4])

---

## 4. Expose the secret to Kubernetes with External Secrets Operator

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: envoy-oauth-secrets
  namespace: istio-system        # or the workload ns for SIDECAR_INBOUND
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: gsm-store              # SecretStore using Workload Identity
    kind: SecretStore
  target:
    name: envoy-oauth-secrets    # K8s Secret ESO will materialise
    creationPolicy: Owner
  dataFrom:
  - extract:
      key: ENVOY_CRED_BUNDLE     # GSM secret name
```

ESO’s GCP provider allows you to link a K8s ServiceAccount to GSM with Workload Identity, eliminating long-lived JSON keys. ([External Secrets][5], [External Secrets][6])

---

## 5. Mount the secret into Envoy

### 5.1 Ingress Gateway Deployment

```yaml
volumes:
- name: envoy-creds
  secret:
    secretName: envoy-oauth-secrets
    defaultMode: 0440
containers:
- name: istio-proxy
  volumeMounts:
  - name: envoy-creds
    mountPath: /etc/istio/creds     # hmac.yaml & token-secret.yaml appear here
    readOnly: true
```

Istio automatically detects mounted files inside the proxy container. ([Istio][7])

### 5.2 Sidecar-injected workloads

```yaml
metadata:
  annotations:
    sidecar.istio.io/userVolume: |
      [{"name":"oauth-secrets","secret":{"secretName":"envoy-oauth-secrets"}}]
    sidecar.istio.io/userVolumeMount: |
      [{"name":"oauth-secrets","mountPath":"/etc/istio/creds","readOnly":true}]
```

The annotations instruct the injector to add the secret volume only to selected Pods. ([Istio][8])

---

## 6. Attach the OAuth2 filter with an EnvoyFilter

### 6.1 Gateway variant (simplified)

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: oauth2-gateway
  namespace: istio-system
spec:
  priority: 10
  workloadSelector:
    labels:
      istio: ingressgateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
      listener:
        portNumber: 8443
        filterChain:
          filter:
            name: envoy.filters.network.http_connection_manager
            subFilter:
              name: envoy.filters.http.router
    patch:
      operation: INSERT_FIRST
      value:
        name: envoy.filters.http.oauth2
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
          config:
            authorization_endpoint: https://idp.example/auth
            token_endpoint:
              cluster: idp-oauth
              uri: https://idp.example/token
              timeout: 5s
            redirect_uri: "%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback"
            credentials:
              client_id: demo-app
              token_secret:
                name: token
                sds_config: { path: /etc/istio/creds/token-secret.yaml }
              hmac_secret:
                name: hmac
                sds_config: { path: /etc/istio/creds/hmac.yaml }
            auth_scopes: ["openid","profile","email"]
            forward_bearer_token: true
            use_refresh_token: true
```

The sidecar version is identical except `context: SIDECAR_INBOUND` and a `workloadSelector` pointing at the app label. ([Envoy Proxy][2], [Istio][1])

---

## 7. Validation checklist

| Check              | Command                                          |                                   |
| ------------------ | ------------------------------------------------ | --------------------------------- |
| Secret YAML syntax | `istioctl validate -f hmac.yaml`                 |                                   |
| ESO synced secret  | `kubectl get secret envoy-oauth-secrets -n <ns>` |                                   |
| Envoy sees secrets | \`pilot-agent request GET config\_dump …         | jq '.static\_resources.secrets'\` |
| Filter inserted    | `istioctl proxy-config listener <pod> -n <ns>`   |                                   |

---

## 8. Production best practices

* **CSRF protection** – pair the OAuth2 filter with Envoy’s CSRF HTTP filter. ([Envoy Proxy][2])
* **Health probes passthrough** – add `pass_through_matcher` rules for `/healthz/*` and similar paths to avoid authentication loops. ([Gist][9])
* **Secret rotation** – upload a new GSM version, then update the `ExternalSecret` with `version:`; Istio hot-reloads the files without restarting the proxy. ([Google Cloud][3])
* **Least-privilege IAM** – grant only `roles/secretmanager.secretAccessor` to the service account used by ESO. ([External Secrets][6])
* **Namespace isolation** – keep gateway secrets in `istio-system`; sidecar secrets in workload namespaces to avoid accidental cross-tenant reads. ([Istio][7])
* **Config reuse** – template secrets, ESO manifests and EnvoyFilters with Helm or Kustomize to eliminate copy-paste drift.
* **Version pinning** – monitor Envoy/Istio release notes for changes in the OAuth2 filter and test patches in staging first. ([Istio][1])

---

### References (key sources)

1. Envoy OAuth2 filter docs – requirements for `token` & `hmac` secrets ([Envoy Proxy][2])
2. EnvoyFilter API reference – contexts, patches, ordering ([Istio][1])
3. Istio annotations for sidecar volume injection ([Istio][8])
4. Secret creation & mounting in gateways (file-mount pattern) ([Istio][7])
5. Google Cloud CLI: add secret versions & set project ([Google Cloud][3], [Google Cloud][4])
6. External Secrets Operator with Google SM provider ([External Secrets][5], [External Secrets][6])

Following this recipe yields a repeatable, IaC-friendly path from secret generation to live OAuth2 enforcement in your service mesh.

[1]: https://istio.io/latest/docs/reference/config/networking/envoy-filter/ "Istio / Envoy Filter"
[2]: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/oauth2_filter "OAuth2 — envoy 1.35.0-dev-84fa7a documentation"
[3]: https://cloud.google.com/secret-manager/docs/add-secret-version "Add a secret version  |  Secret Manager Documentation  |  Google Cloud"
[4]: https://cloud.google.com/sdk/docs/properties?utm_source=chatgpt.com "Managing gcloud CLI properties | Google Cloud CLI Documentation"
[5]: https://external-secrets.io/v0.5.8/provider-google-secrets-manager/ "Secret Manager - External Secrets Operator"
[6]: https://external-secrets.io/latest/provider/google-secrets-manager/ "Google Cloud Secret Manager - External Secrets Operator"
[7]: https://istio.io/v1.4/docs/tasks/traffic-management/ingress/secure-ingress-mount/ "Istioldie 1.4 / Secure Gateways (File Mount)"
[8]: https://istio.io/latest/docs/reference/config/annotations/ "Istio / Resource Annotations"
[9]: https://gist.github.com/jdgomeza/9cb11fedffb09924ed410c666cc06ad1?utm_source=chatgpt.com "Istio OAuth2 Envoy Filter (Okta example) - gists · GitHub"
