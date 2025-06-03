Below is a self-contained, production-ready guide (in English) that distills the long Russian walkthrough you shared into a concise set of best-practice instructions.  It is organized so that a Platform / DevOps engineer can choose either **GATEWAY** or **SIDECAR\_INBOUND** context for Envoy's OAuth2 filter, prepare the required secrets once, and reuse the same artefacts across environments.

---

## 1  Overview

Istio allows you to insert Envoy's `oauth2` HTTP filter either:

| Context              | Where the filter runs                     | Where the Kubernetes Secret must live |
| -------------------- | ----------------------------------------- | ------------------------------------- |
| **GATEWAY**          | On the Ingress Gateway pod (Layer-7 edge) | `istio-system` namespace              |
| **SIDECAR\_INBOUND** | On each workload sidecar proxy            | Application namespace                 |

The two contexts share the same **secret bundle**- a JSON object that embeds two Envoy SDS Secret resources:

1. `hmac.yaml` - an HMAC signing key
2. `token-secret.yaml` - the client's `client_secret` (a long-lived, confidential value)

Those two YAML files are mounted read-only in the container at `/etc/istio/creds`, where Envoy can load them via the SDS **`path_config_source`** mechanism.([Envoy Proxy][1], [Istio][2])

---

## 2  Prerequisites

| Tool                            | Purpose                                                                                  |                                        |
| ------------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------- |
| `gcloud` CLI                    | Manage Google Secret Manager (GSM)                                                       | ([Google Cloud][3], [Google Cloud][4]) |
| `jq` & `yq`                     | JSON <-> YAML manipulation                                                                 |                                        |
| `python > 3.6`                  | Generate cryptographically strong keys via `secrets` library ([Python documentation][5]) |                                        |
| `kubectl` / `istioctl`          | Apply manifests and validate Envoy configs ([Istio][2])                                  |                                        |
| External Secrets Operator (ESO) | Sync GSM -> Kubernetes Secret ([External Secrets][6])                                     |                                        |

Ensure you have cluster-admin access to the target GKE/GKE-on-prem cluster and that Istio is already installed.

---

## 3  Generate and Package Secrets

### 3.1  Create an HMAC key

```bash
python3 - <<'PY'
import secrets, textwrap, sys
key = secrets.token_hex(32)
print(key)
PY
```

### 3.2  Author the SDS files

```bash
cat > hmac.yaml <<EOF
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: hmac
  generic_secret:
    secret:
      inline_string: ${HMAC_KEY}
EOF

cat > token-secret.yaml <<EOF
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: token
  generic_secret:
    secret:
      inline_string: ${CLIENT_SECRET}
EOF
```

> **Tip:** Use [`istioctl validate`](https://istio.io/latest/docs/reference/commands/istioctl/#istioctl-validate) to confirm each YAML is a valid Envoy resource.([Istio][2])

### 3.3  Bundle the secrets as JSON

```bash
jq -n --rawfile h hmac.yaml --rawfile t token-secret.yaml \
   '{ "hmac.yaml": $h, "token-secret.yaml": $t }' > oauth-secrets.json
```

---

## 4  Store in Google Secret Manager

1. **Authenticate** and select your project:

   ```bash
   gcloud auth login
   gcloud config set project $PROJECT_ID
   ```

2. **Add a new secret *version*** (or create the secret if it doesn't exist):

   ```bash
   gcloud secrets versions add ENVOY_CRED_BUNDLE \
         --data-file=oauth-secrets.json
   ```

   ([Google Cloud][3])

3. Record the newly created version number (e.g., `5`) for use in the ESO manifest.

---

## 5  Sync GSM -> Kubernetes with External Secrets Operator

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: envoy-oauth-secrets
  namespace: istio-system          # for GATEWAY; change for SIDECAR case
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: gsm-store
    kind: SecretStore
  target:
    name: envoy-oauth-secrets
    creationPolicy: Owner
  dataFrom:
  - extract:
      key: ENVOY_CRED_BUNDLE
      version: "5"                 # GSM version to sync
```

ESO writes an **opaque** `Secret` containing the two SDS YAMLs, exactly as Envoy expects.([External Secrets][6])

---

## 6  Mount the Secret

### 6.1  Ingress Gateway (GATEWAY context)

Edit the gateway `Deployment` (or use `IstioOperator` overlays):

```yaml
spec:
  template:
    spec:
      volumes:
      - name: envoy-creds
        secret:
          secretName: envoy-oauth-secrets
          defaultMode: 0440
      containers:
      - name: istio-proxy
        volumeMounts:
        - name: envoy-creds
          mountPath: /etc/istio/creds
          readOnly: true
```

The two files appear at:

```
/etc/istio/creds/hmac.yaml
/etc/istio/creds/token-secret.yaml
```

Mounting secrets in the gateway pod follows the same pattern used for TLS certs.([Istio][7])

### 6.2  Workload Sidecar (SIDECAR\_INBOUND context)

Add annotations to the **workload** `Deployment` or `Pod` spec:

```yaml
metadata:
  annotations:
    sidecar.istio.io/userVolume: |
      [{"name":"oauth-secrets","secret":{"secretName":"envoy-oauth-secrets"}}]
    sidecar.istio.io/userVolumeMount: |
      [{"name":"oauth-secrets","mountPath":"/etc/istio/creds","readOnly":true}]
```

Istio injector merges these volumes into the sidecar proxy.([Istio][8], [Istio][9])

---

## 7  Define the Envoy Filter

Below are **diff-friendly** snippets-you need only swap the `context` and `namespace` to move between GATEWAY and SIDECAR\_INBOUND.

### 7.1  Filter template (common parts)

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: oauth2-filter
  namespace: istio-system        # default -> app namespace for sidecar mode
spec:
  priority: 10
  workloadSelector:
    labels:
      istio: ingressgateway     # or app label for sidecar mode
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY          # or SIDECAR_INBOUND
      listener:
        portNumber: 8443        # omit for inbound
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
              cluster: idp-oauth-cluster
              uri: https://idp.example/token
              timeout: 5s
            redirect_uri: "%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback"
            redirect_path_matcher:
              path: { exact: /callback }
            signout_path:
              path: { exact: /logout }
            credentials:
              client_id: my-test-app
              token_secret:
                name: token
                sds_config: { path: /etc/istio/creds/token-secret.yaml }
              hmac_secret:
                name: hmac
                sds_config: { path: /etc/istio/creds/hmac.yaml }
              cookie_domain: ".example"
              cookie_names:
                bearer_token: BearerToken
                oauth_expires: OauthExpires
            auth_scopes: ["openid", "profile", "email"]
            forward_bearer_token: true
            use_refresh_token: true
  # Cluster definition (identical in both modes) ...
```

Configuration keys follow Envoy's upstream docs.([Envoy Proxy][1], [Envoy Proxy][10])

---

## 8  Validation & Troubleshooting

1. **Lint** the filter:

   ```bash
   istioctl validate -f oauth-filter.yaml
   ```
2. **Confirm Envoy loads the secrets** (inside the proxy container):

   ```bash
   curl localhost:15000/config_dump | jq '.configs[] | select(.type_url | contains("envoy.secret"))'
   ```
3. **Watch the OAuth flow** with `istioctl pc log <pod> --level misc:debug`.

If the filter works in sidecar but not gateway, ensure the secrets are mounted on the gateway pod; this is a common pitfall.([GitHub][11])

---

## 9  Security & Operational Tips

* **Rotate secrets** by publishing a new GSM version and allowing ESO to refresh. No redeploy is needed; Envoy hot-reloads SDS files.
* **Least privilege**: scope the secret only to Envoy; don't reuse the HMAC key for other services.
* **Automate**: simplify with Kustomize overlays or an `IstioOperator` profile for multi-cluster rollout.
* **Audit**: enable Google Secret Manager audit logs and Istio telemetry to detect failed auth attempts.

---

## 10  References

1. Envoy OAuth2 filter configuration docs ([Envoy Proxy][1])
2. Envoy OAuth2 v3 API proto ([Envoy Proxy][10])
3. Istio EnvoyFilter CRD docs ([Istio][12])
4. Istio `sidecar.istio.io/userVolume*` annotations ([Istio][8], [Istio][9])
5. Google Secret Manager "Add secret version" ([Google Cloud][3], [Google Cloud][4])
6. External Secrets Operator overview ([External Secrets][6])
7. Python `secrets` module for key generation ([Python documentation][5])
8. Secret mount pattern for TLS on Ingress Gateway (analogue for OAuth2) ([Istio][7])
9. Gateway volume-mount issue (common troubleshooting case) ([GitHub][11])
10. `istioctl` command reference for validation ([Istio][2])

Use this template as a baseline in your Git repository or runbook; parameterize values (`client_id`, IDP endpoints, namespaces) via Helm/Kustomize to ensure repeatability across clusters.

[1]: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/oauth2_filter?utm_source=chatgpt.com "OAuth2 - envoy 1.35.0-dev-c12fef documentation"
[2]: https://istio.io/latest/docs/reference/commands/istioctl/?utm_source=chatgpt.com "Istio / istioctl"
[3]: https://cloud.google.com/secret-manager/docs/add-secret-version?utm_source=chatgpt.com "Add a secret version | Secret Manager Documentation - Google Cloud"
[4]: https://cloud.google.com/sdk/gcloud/reference/secrets/versions/add?utm_source=chatgpt.com "gcloud secrets versions add | Google Cloud CLI Documentation"
[5]: https://docs.python.org/3/library/secrets.html?utm_source=chatgpt.com "secrets - Generate secure random numbers for managing secrets ..."
[6]: https://external-secrets.io/?utm_source=chatgpt.com "External Secrets Operator: Introduction"
[7]: https://istio.io/v1.4/docs/tasks/traffic-management/ingress/secure-ingress-mount/?utm_source=chatgpt.com "Secure Gateways (File Mount) - Istio"
[8]: https://istio.io/latest/docs/reference/config/annotations/?utm_source=chatgpt.com "Resource Annotations - Istio"
[9]: https://istio.io/v1.19/docs/reference/config/annotations/?utm_source=chatgpt.com "Istioldie 1.19 / Resource Annotations"
[10]: https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/http/oauth2/v3/oauth.proto?utm_source=chatgpt.com "OAuth (proto) - envoy 1.35.0-dev-c12fef documentation"
[11]: https://github.com/istio/istio/issues/36999?utm_source=chatgpt.com "Unable to mount volumes to ingress gateway pod using istio ..."
[12]: https://istio.io/latest/docs/reference/config/networking/envoy-filter/?utm_source=chatgpt.com "Envoy Filter - Istio"
