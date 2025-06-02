Great. I’ll create a step-by-step guide in English on how to configure an Envoy OAuth2 filter using Istio, supporting both SIDECAR\_INBOUND and GATEWAY contexts. This guide will preserve the original YAML and Bash examples, while improving clarity, formatting, and following best practices.

I’ll let you know as soon as it’s ready for your review.


# Configuring Envoy’s OAuth2 Filter in Istio (Gateway and Sidecar Inbound)

**Overview:** This step-by-step guide explains how to set up Envoy’s built-in OAuth2 authentication filter in an Istio service mesh. We will cover both **GATEWAY** and **SIDECAR\_INBOUND** deployment contexts, with detailed instructions on generating secrets, mounting them, and configuring EnvoyFilters. By the end, you’ll have a working OAuth2 flow either at the ingress gateway (cluster edge) or at a specific service’s sidecar, complete with best practices for security and maintainability.

## 1. Understand Envoy Filter Contexts: GATEWAY vs SIDECAR\_INBOUND

EnvoyFilters in Istio can be applied at different **contexts** (positions in the traffic flow). The two contexts relevant for end-user OAuth2 authentication are:

* **GATEWAY Context:** Applies the filter at the Istio **ingress gateway**, i.e. the mesh’s edge. This means all external requests entering through the gateway will be subject to OAuth2. This is typically used to enforce a login for any external user traffic at the cluster’s front door. It’s considered best practice to install the OAuth2 filter at the first point of external connectivity (the ingress gateway) so that all inbound traffic is authenticated globally.

* **SIDECAR\_INBOUND Context:** Applies the filter at the **sidecar proxy** of a specific service, intercepting traffic inbound to that service’s pod. Use this if you need to protect individual services (for example, internal UIs or selectively exposed apps) with OAuth2, rather than the entire gateway. This can be useful for multi-tenant scenarios or if different services use different OAuth providers or settings.

**When to use which?** If you want a single OAuth2 login protecting all incoming traffic to the mesh, use the GATEWAY context on the ingress. If you only want certain applications to require OAuth2 (and perhaps others open or using other auth methods), use SIDECAR\_INBOUND on those specific workloads. It’s possible to use both in one mesh (for example, a global login on the gateway and an additional OAuth2 flow for a particular service), but typically you’d choose one approach based on requirements.

> **Note:** The EnvoyFilter `context` field cannot list multiple contexts at once – it’s an enum value. To support both gateway and sidecar, you will either create **two EnvoyFilter resources** or duplicate the configuration within one resource (using YAML anchors to avoid repetition). In this guide we will show separate configurations for clarity.

## 2. Generate OAuth2 Secrets (HMAC Key & Token Secret)

Envoy’s OAuth2 filter requires two secret values which must be provided as local files in the Envoy proxy:

* **OAuth2 Client Secret (“token\_secret”):** This is the **client secret** of your OAuth2/OIDC application. It’s provided by your identity provider (e.g. Google, Auth0, Okta) when you register an OAuth2 client. Envoy uses this to exchange the authorization code for a token. **Do not store this in code or git** – treat it as sensitive credentials.

* **HMAC Key (“hmac\_secret”):** This is a random secret used by Envoy to sign the access token and expiry cookies (to prevent tampering). It should be a strong random key (e.g. 256-bit) and kept secret just like the client secret.

We will package these secrets in **Envoy SDS (Secret Discovery Service) format** as YAML files. This format is basically an Envoy `Secret` resource with the secret material embedded, which Envoy will load from disk.

### 2.1 Create SDS YAML for the Secrets

1. **Generate a random HMAC key:** Use a command like `head -c 32 /dev/urandom | base64` to generate 32 bytes of random data and Base64-encode them. This output will be our HMAC key (256-bit encoded in Base64).

2. **Prepare the `token-secret.yaml`:** This file will contain your OAuth2 client secret (provided by your IdP). We will use `inline_string` for this since it’s a text value. Example content (replace placeholders with your actual client secret):

   ```yaml
   # token-secret.yaml
   resources:
   - "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
     name: token                  # name must match reference in EnvoyFilter
     generic_secret:
       secret:
         inline_string: "<YOUR_OAUTH2_CLIENT_SECRET>"
   ```

3. **Prepare the `hmac-secret.yaml`:** This file will contain the random key generated in step 1. We’ll use `inline_bytes` for binary data. Example content (with a placeholder for the generated key):

   ```yaml
   # hmac-secret.yaml
   resources:
   - "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
     name: hmac                   # name must match reference in EnvoyFilter
     generic_secret:
       secret:
         # 32-byte random key, Base64 encoded:
         inline_bytes: <BASE64_RANDOM_HMAC_KEY>
   ```

   For example, if your generated HMAC Base64 string is `XYJ7ibKwXwmRrO/yL/37ZV+T3Q/WB+xfhmVlio+wmc0=`, it would be placed after `inline_bytes:`. (The sample above was generated with `head -c 32 /dev/urandom | base64`.)

**Important:** Ensure the `name` fields (`token` and `hmac`) exactly match what we’ll reference in the EnvoyFilter later. Also, **do not commit these YAML files to source control** since they contain sensitive secrets.

### 2.2 Create a Kubernetes Secret from the SDS files

Next, we need to provide these secret files to Envoy proxies. The typical approach is to store them in a Kubernetes Secret (of type Opaque) and mount them as files in the Envoy container. We will create a K8s secret containing both `token-secret.yaml` and `hmac-secret.yaml` as data keys.

You can create the secret via kubectl in two ways:

* **Option A:** Using `kubectl create secret --from-file`:

  ```bash
  # Replace <NAMESPACE> with the namespace where the proxy runs.
  # For an ingress gateway, this is usually "istio-system".
  NAMESPACE="istio-system"
  kubectl create secret generic istio-oauth2-secret \
    --from-file=token-secret.yaml \
    --from-file=hmac-secret.yaml \
    -n "$NAMESPACE"
  ```

  This command will create a secret named `istio-oauth2-secret` in the given namespace, with keys and values from the files. The secret’s data will be Base64-encoded automatically.

* **Option B:** Manually base64-encode the files and write a YAML manifest:

  First, base64 encode each file (on Linux/macOS):

  ```bash
  export TOKEN_B64=$(base64 -w0 token-secret.yaml)
  export HMAC_B64=$(base64 -w0 hmac-secret.yaml)
  echo "$TOKEN_B64"   # print to verify, if needed
  echo "$HMAC_B64"    # print to verify, if needed
  ```

  Then create a manifest `istio-oauth2-secret.yaml` as below, inserting the Base64 strings for each data item:

  ```yaml
  apiVersion: v1
  kind: Secret
  metadata:
    name: istio-oauth2-secret
    namespace: <NAMESPACE>
  type: Opaque
  data:
    token-secret.yaml: "<BASE64_ENCODED_CONTENT_OF_TOKEN_YAML>"
    hmac-secret.yaml: "<BASE64_ENCODED_CONTENT_OF_HMAC_YAML>"
  ```

  Apply this with `kubectl apply -f istio-oauth2-secret.yaml`.

Either method results in a Kubernetes Secret where the keys `token-secret.yaml` and `hmac-secret.yaml` contain the Envoy SDS secret definitions (in Base64 form). We will mount this secret in the Envoy proxies so that the files appear at runtime.

> **Why a Kubernetes Secret?** Using a Secret object ensures the data is base64-encoded and can be configured with access restrictions. Avoid using ConfigMaps for sensitive data like OAuth2 client secrets. In fact, one user’s OAuth2 filter failed until they switched to using a Secret and mounted it properly.

## 3. Store Secrets in Google Secret Manager (for Security & Rotation)

While Kubernetes Secrets provide in-cluster storage, it’s a best practice to also store your sensitive secrets in a secure external vault. If you’re on GCP, **Google Secret Manager (GSM)** is a convenient option. GSM provides versioning, access control, and auditing for secrets.

**Steps to store in GSM:**

* **Create secrets in GSM:** Use the gcloud CLI or Console to create secrets for the OAuth2 credentials. For example:

  ```bash
  # Store the HMAC key in GSM
  echo -n "$HMAC_KEY_BASE64" | gcloud secrets create istio-oauth-hmac-key \
      --data-file=- --replication-policy="automatic"

  # Store the OAuth2 client secret in GSM
  echo -n "<YOUR_OAUTH_CLIENT_SECRET>" | gcloud secrets create istio-oauth-client-secret \
      --data-file=- --replication-policy="automatic"
  ```

  Replace the names with something appropriate for your context. We use `automatic` replication for simplicity (GSM will replicate to multiple regions).

* **Secret versioning:** Each time you need to rotate or update a secret, you don’t create a new secret, but add a new **version** to the existing secret:

  ```bash
  # Example: rotate HMAC key
  NEW_HMAC=$(head -c 32 /dev/urandom | base64)
  echo -n "$NEW_HMAC" | gcloud secrets versions add istio-oauth-hmac-key --data-file=-
  ```

  GSM will keep the old version(s) and mark the latest with an incrementing version number. You can configure your workloads to fetch either a specific version or the latest.

* **Using GSM secrets in Kubernetes:** You have a few options:

  1. Manually retrieve the secret values and update the Kubernetes Secret (as done in section 2.2). For example, use `gcloud secrets versions access latest --secret=istio-oauth-hmac-key` in your CI/CD pipeline to fetch the value and plug it into your manifest or kubectl command.
  2. Use a **Secret Manager CSI driver** or an **external secrets operator** to automatically fetch and update Kubernetes Secrets from GSM. This way, your cluster can load secrets at runtime without them ever being stored in git. (This is an advanced setup beyond the scope of this guide, but worth considering for production.)

**Best Practice:** Storing secrets in GSM means you have a secure, audited source of truth outside the cluster. Keep the GSM secret names and versions noted, and restrict access to them. When rotating, update GSM first (creating a new version), then update the Kubernetes Secret to match (Envoy will need the new secret file on next startup/reload).

## 4. Mounting Secrets into Envoy Pods

Now that we have our secrets in a Kubernetes Secret (`istio-oauth2-secret`), we need to mount them so that Envoy can read the files at runtime. Envoy (as deployed by Istio) will be looking for the files at the specific paths we configured (`/etc/istio/config/token-secret.yaml` and `/etc/istio/config/hmac-secret.yaml` in our EnvoyFilter config). We must ensure those paths exist with the correct content in the Envoy container.

There are two scenarios:

### 4.1 Mounting on the Ingress Gateway (GATEWAY context)

For an Istio ingress gateway (often running in the `istio-system` namespace), we add a volume to the gateway Deployment (or StatefulSet) and mount it into the Envoy container:

* **Identify the gateway pod**: Typically the ingress gateway is a Deployment named `istio-ingressgateway` (in Istio 1.x) with a container `istio-proxy`. Confirm the name and namespace (`istio-system` by default).

* **Add a Secret volume**: Modify the gateway pod spec to include a volume sourcing our secret, and a corresponding volume mount in the Envoy container. For example, in the Deployment spec:

  ```yaml
  apiVersion: apps/v1
  kind: Deployment
  metadata:
    name: istio-ingressgateway
    namespace: istio-system
  spec:
    template:
      spec:
        volumes:
          - name: oauth2-secrets
            secret:
              secretName: istio-oauth2-secret    # our secret containing YAML files
        containers:
          - name: istio-proxy
            volumeMounts:
              - name: oauth2-secrets
                mountPath: /etc/istio/config               # mount whole secret here
                readOnly: true
  ```

  This will project each key of the secret as a file under `/etc/istio/config`. In particular, we’ll get:

  * `/etc/istio/config/token-secret.yaml`
  * `/etc/istio/config/hmac-secret.yaml`

  Make sure the filenames match exactly what you used in the EnvoyFilter (`path: "/etc/istio/config/token-secret.yaml"` etc). The volume is marked read-only for safety.

* **Apply the changes**: If you’re editing the manifest directly, apply it (or if using `kubectl patch`, ensure the JSON path is correct). After updating, restart the gateway pod (if not automatically restarted) to ensure it picks up the new volume.

If you installed Istio via the IstioOperator (Helm or Operator API), you can achieve the same without manual edits:

* IstioOperator allows specifying `spec.components.ingressGateways[*].k8s.volumeMounts` and `volumes`, or using `podAnnotations`. For instance, you could set a `podAnnotation` to utilize the same mechanism as sidecar injection. For example:

  ```yaml
  podAnnotations:
    sidecar.istio.io/userVolume: '[{"name":"oauth2-secrets","secret":{"secretName":"istio-oauth2-secret"}}]'
    sidecar.istio.io/userVolumeMount: '[{"name":"oauth2-secrets","mountPath":"/etc/istio/config","readonly":true}]'
  ```

  in the gateway’s spec. Istio will apply these annotations to the gateway pod template, thereby mounting the secret just as with a sidecar. (Under the hood, the Istio sidecar injector can also act on gateway pods if annotations are present.)

Regardless of approach, once done, the ingress gateway’s Envoy container will have the required secret files. This prevents the “file not found” errors in Envoy. (If misconfigured, Envoy will log an error like *“paths must refer to an existing path… '/etc/istio/config/token-secret.yaml' does not exist”*, indicating the mount failed or secret is missing.)

### 4.2 Mounting in Application Sidecars (SIDECAR\_INBOUND context)

For sidecar proxies in application pods, we use **pod annotations** to inject the volume, since we typically don’t manage the Envoy container spec directly (it’s auto-injected by Istio).

In each Deployment (or PodTemplate) of the app that needs OAuth2 protection:

1. Ensure the secret with the SDS files exists in the **same namespace** as the app. You can either create the same `istio-oauth2-secret` in that namespace (with the same data) or use a different name and adjust accordingly. For simplicity, let’s assume each namespace has its own copy of the secret (you can script this or use a secret distribution mechanism).

2. Add the following annotations to the pod template metadata in the Deployment (YAML snippet):

   ```yaml
   template:
     metadata:
       annotations:
         sidecar.istio.io/userVolume: '[{"name":"oauth2-secrets","secret":{"secretName":"istio-oauth2-secret"}}]'
         sidecar.istio.io/userVolumeMount: '[{"name":"oauth2-secrets","mountPath":"/etc/istio/config","readonly":true}]'
   ```

   This JSON-in-YAML is an Istio annotation that tells the sidecar injector to add a volume and mount. In the example above:

   * We name the volume `oauth2-secrets` (arbitrary name, just must match in both annotations).
   * We reference the secret by name (`istio-oauth2-secret`).
   * We mount it at `/etc/istio/config` inside the sidecar (Envoy) container, read-only.

   Make sure to keep the annotation value as a valid JSON string (note the use of single quotes wrapping the JSON). The above will result in the same file paths inside the sidecar as we had for the gateway.

3. Deploy the application (or update it). When the sidecar is injected, it will include our custom volume and mount. You can verify by describing the pod and checking the `istio-proxy` container’s volume mounts.

With this setup, the Envoy proxy in the application pod now has `token-secret.yaml` and `hmac-secret.yaml` at `/etc/istio/config/`. This addresses the issue of the filter not finding the secret files (as encountered by others before).

## 5. Configure the Envoy OAuth2 Filter via EnvoyFilter

Finally, we configure Envoy to use the OAuth2 filter. We do this by creating an **EnvoyFilter** resource that patches the Envoy configuration. We will create two variants: one for the gateway and one for sidecars. The core configuration (OAuth2 endpoints, client ID, etc.) will be similar in both.

**What the EnvoyFilter does:**

* It **adds a cluster** for the external OAuth2 provider (so Envoy can reach the provider’s authorization and token endpoints).
* It **inserts the OAuth2 HTTP filter** into the HTTP filter chain, with the specified settings (auth endpoints, redirect paths, secrets, etc.).

We’ll provide complete example YAMLs for each context. You can adapt the values (client ID, endpoints, domain, etc.) to your OAuth provider. In these examples, we’ll assume a generic OAuth2 provider – replace values with those for Google, Okta, Auth0, or your chosen IdP:

### 5.1 EnvoyFilter for an Ingress Gateway (GATEWAY Context)

In this example, we protect all traffic going through the Istio ingress gateway. We’ll target the EnvoyFilter to the gateway’s pods via a label selector, and insert the filter with `context: GATEWAY`.

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: oauth2-gateway-filter
  namespace: istio-system    # usually place in same ns as gateway (istio-system)
spec:
  workloadSelector:
    labels:
      istio: ingressgateway   # target the ingress-gateway pod(s) (default label in Istio)
  configPatches:
  # 1. Add an OAuth cluster for the IdP (to reach auth & token endpoints)
  - applyTo: CLUSTER
    match:
      cluster:
        # Match on cluster name to avoid conflicts (or use address)
        service: oauth
    patch:
      operation: ADD
      value:               # defines a new cluster named "oauth"
        name: oauth
        type: LOGICAL_DNS
        connect_timeout: 5s
        lb_policy: ROUND_ROBIN
        dns_lookup_family: V4_ONLY                # use IPv4 (adjust if IPv6 needed)
        load_assignment:
          cluster_name: oauth
          endpoints:
          - lb_endpoints:
            - endpoint:
                address:
                  socket_address:
                    address: <OAUTH_PROVIDER_HOST>   # e.g. accounts.google.com or your Okta domain
                    port_value: 443
        transport_socket:
          name: envoy.transport_sockets.tls
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
            sni: <OAUTH_PROVIDER_HOST>               # e.g. accounts.google.com
  # 2. Insert the OAuth2 filter into HTTP filter chain on the gateway
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
      listener:
        filterChain:
          filter:
            name: envoy.filters.http.connection_manager       # HTTP connection manager
            # Insert before router or JWT auth filter:
            subFilter:
              name: envoy.filters.http.jwt_authn              # if a JWT filter is in use
              # (If no JWT auth filter is configured on gateway, use envoy.filters.http.router here)
    patch:
      operation: INSERT_BEFORE
      value:    # The OAuth2 filter configuration
        name: envoy.filters.http.oauth2
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
          config:
            authorization_endpoint: "https://<OAUTH_PROVIDER_HOST>/oauth2/v1/authorize"
            token_endpoint:
              cluster: oauth
              uri: "https://<OAUTH_PROVIDER_HOST>/oauth2/v1/token"
              timeout: 5s
            redirect_uri: "https://%REQ(:authority)%/_oauth2/callback"
            redirect_path_matcher:
              path:
                exact: /_oauth2/callback
            signout_path:
              path:
                exact: /signout
            credentials:
              client_id: "<YOUR_OAUTH2_CLIENT_ID>"
              token_secret:
                name: token
                sds_config:
                  path: "/etc/istio/config/token-secret.yaml"
              hmac_secret:
                name: hmac
                sds_config:
                  path: "/etc/istio/config/hmac-secret.yaml"
            # Optional settings:
            auth_scopes: ["openid", "profile", "email"]   # scopes to request; adjust as needed
            forward_bearer_token: true    # forward the token as Authorization header to backend
            pass_through_matcher:
            - name: :path
              exact_match: /healthz/ready  # example: bypass auth for health check endpoint
```

Let’s break down the important parts of this configuration:

* We use a `workloadSelector` to only apply this EnvoyFilter to pods labeled `istio=ingressgateway` in `istio-system` (the default Istio ingress gateway pods).

* **Cluster patch:** We create a cluster named “oauth” pointing to our IdP’s domain. Replace `<OAUTH_PROVIDER_HOST>` with your provider’s host (for example, `accounts.google.com` or `your-domain.okta.com`). We set up TLS (`transport_socket` with SNI), and a logical DNS resolution for the host. This cluster will be used by the OAuth2 filter to send requests to the IdP (for token exchange, etc.).

* **Filter insertion patch:** We specify `context: GATEWAY` so it only applies to the gateway’s listener. We match on the HTTP connection manager’s filter chain. In the `subFilter` match, we used `envoy.filters.http.jwt_authn` – meaning “insert our filter before the JWT auth filter.” This assumes you might have a JWT authentication filter configured (for instance, via an Istio `RequestAuthentication` policy). If you do, placing the OAuth2 filter before it ensures that once a user is authenticated, the JWT filter can verify the token signature. If you are not using any JWT verification filter on the gateway, you can change `subFilter` to `envoy.filters.http.router` to insert the OAuth2 filter before the router (which means at the end of the chain).

* **OAuth2 filter config:**

  * `authorization_endpoint` and `token_endpoint` are the URLs of your provider’s OAuth2 authorization and token endpoints. The values in the example (with `/oauth2/v1/authorize` and `/oauth2/v1/token`) are typical for providers like Okta. For Google, you would use `https://accounts.google.com/o/oauth2/v2/auth` for authorization, and `https://oauth2.googleapis.com/token` for the token endpoint. Adjust these as needed for your IdP.
  * `redirect_uri`: This is the URL where the IdP will redirect back to, after the user logs in. We set it to use the same host that the user was accessing (`%REQ(:authority)%`) and a path `/_oauth2/callback`. You should also configure this exact URI in your OAuth2 provider’s client settings as a valid redirect/callback URL. In this example, if your site is `https://app.example.com`, the redirect URI would be `https://app.example.com/_oauth2/callback`.
  * `redirect_path_matcher`: The filter will intercept requests to this path (the callback path) to complete the OAuth flow. We set it to `/_oauth2/callback` (matching the above). This path should not conflict with any real endpoint in your app.
  * `signout_path`: (Optional) Here set to `/signout`. If a user hits this path, the filter will clear the OAuth cookies (effectively signing the user out locally). You can route this path to a small stub page or just rely on the filter’s behavior. After sign-out, the next request will trigger a fresh OAuth login.
  * **Credentials**: We provide the `client_id` of our OAuth app, and references to the secrets:

    * `token_secret`: This refers to the client secret. We give it a `name` (`token`) and an `sds_config` pointing to the file path. The name must match the one used inside `token-secret.yaml` (we used `name: token` there). The path must match where we mounted the file. We used `/etc/istio/config/token-secret.yaml`, which matches our volume mount.
    * `hmac_secret`: Similarly references the HMAC key file (`hmac-secret.yaml`) with name `hmac`.
  * **Auth scopes**: (Optional) A list of OAuth scopes to request. In OIDC, it’s common to include `openid` plus any other profile info you need (email, profile, etc.). For Google, you must override the default “user” scope (which Envoy uses by default in v1.17) with a valid scope like `openid`, otherwise Google’s auth might fail. The example above includes common OIDC scopes. Adjust or omit as needed for your provider.
  * **forward\_bearer\_token**: When `true`, after a successful login, Envoy will add an `Authorization: Bearer <token>` header to outgoing requests to your service. This is useful if your upstream service or Istio policies need to see the token. For instance, you could have an Istio `RequestAuthentication` + `AuthorizationPolicy` to cryptographically verify and authorize the JWT in the mesh. If you don’t need the header forwarded (maybe your app purely uses the cookies), you can set this to false.
  * **pass\_through\_matcher**: (Optional) This lets you specify certain requests that should bypass the OAuth filter (i.e., not trigger a redirect). In the example, we allow the path `/healthz/ready` to pass through without authentication. This is useful for health checks or endpoints that need to be accessible without login (like a status or metrics endpoint). You can add multiple matchers if needed (matching by path, prefix, etc.).

Apply this EnvoyFilter with `kubectl apply -f`. Once applied, it will patch the running gateway Envoy. If everything is set up correctly (and the secret files are mounted properly), the gateway will immediately start enforcing OAuth2.

**Expected behavior:** When you visit a URL served by the gateway (e.g., your app’s URL), if you have no OAuth2 session yet, Envoy will redirect you to the `authorization_endpoint`. You’ll see your IdP’s login page. After authenticating, the IdP will redirect you back to the Envoy’s `redirect_uri` (`/_oauth2/callback` path on your host). Envoy will intercept that, exchange the code for a token by calling the `token_endpoint` (using the client secret), then set several cookies on the user’s browser: typically `BearerToken` (the JWT token or opaque token), `OauthHMAC` (an HMAC signature of the token), and `OauthExpires` (the token expiry timestamp). It then redirects the user to the originally requested page. Subsequent requests will include the cookies; Envoy will validate them (check HMAC and expiry) and, if `forward_bearer_token` is enabled, pass the token in the Authorization header upstream. Your app will see requests from authenticated users.

### 5.2 EnvoyFilter for a Sidecar Proxy (SIDECAR\_INBOUND Context)

Now, suppose instead of at the gateway, we want to enforce OAuth2 on traffic to a specific service’s sidecar (for example, a particular frontend service). The configuration is very similar, but we will use `context: SIDECAR_INBOUND` and target the EnvoyFilter to that service’s workload.

Let’s say our application is labeled `app: myapp` in namespace `myapp-ns`. We created the secret in that namespace and annotated the Deployment as described in section 4.2. Now the EnvoyFilter:

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: oauth2-sidecar-filter
  namespace: myapp-ns    # place in the same namespace as the workload
spec:
  workloadSelector:
    labels:
      app: myapp         # target only the Envoy in pods of myapp
  configPatches:
  # Add OAuth cluster (same as before, possibly different host if using another IdP)
  - applyTo: CLUSTER
    match:
      cluster:
        service: oauth
    patch:
      operation: ADD
      value:
        name: oauth
        type: LOGICAL_DNS
        connect_timeout: 5s
        lb_policy: ROUND_ROBIN
        dns_lookup_family: V4_ONLY
        load_assignment:
          cluster_name: oauth
          endpoints:
          - lb_endpoints:
            - endpoint:
                address:
                  socket_address:
                    address: <OAUTH_PROVIDER_HOST>
                    port_value: 443
        transport_socket:
          name: envoy.transport_sockets.tls
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
            sni: <OAUTH_PROVIDER_HOST>
  # Insert OAuth2 filter on inbound path for myapp's Envoy
  - applyTo: HTTP_FILTER
    match:
      context: SIDECAR_INBOUND
      listener:
        filterChain:
          filter:
            name: envoy.filters.http.connection_manager
            subFilter:
              name: envoy.filters.http.jwt_authn   # or envoy.filters.http.router if no JWT filter
          # If the service listens on a specific port, you can specify portNumber:
          # portNumber: 80
    patch:
      operation: INSERT_BEFORE
      value:
        name: envoy.filters.http.oauth2
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
          config:
            authorization_endpoint: "https://<OAUTH_PROVIDER_HOST>/oauth2/v1/authorize"
            token_endpoint:
              cluster: oauth
              uri: "https://<OAUTH_PROVIDER_HOST>/oauth2/v1/token"
              timeout: 5s
            redirect_uri: "https://%REQ(:authority)%/oauth2/callback"
            redirect_path_matcher:
              path:
                exact: /oauth2/callback
            signout_path:
              path:
                exact: /signout
            credentials:
              client_id: "<YOUR_OAUTH2_CLIENT_ID>"
              token_secret:
                name: token
                sds_config:
                  path: "/etc/istio/config/token-secret.yaml"
              hmac_secret:
                name: hmac
                sds_config:
                  path: "/etc/istio/config/hmac-secret.yaml"
            auth_scopes: ["openid", "profile", "email"]
            forward_bearer_token: true
            pass_through_matcher:
            - name: :path
              exact_match: /healthz/ready
```

Differences from the gateway config:

* We put this EnvoyFilter in the application’s namespace (`myapp-ns`) and use a `workloadSelector` matching `app: myapp` (or whatever label your pod has). This ensures it only applies to Envoy for that workload, not every sidecar in the namespace.

* `context: SIDECAR_INBOUND` means the filter is applied to inbound listener(s) of the sidecar proxy (traffic coming into the app). You may specify `portNumber` under the listener match if your app only listens on a specific port (for example, 80 or 443). If omitted, it will apply to all inbound ports’ HTTP connection managers. It’s often fine to leave it out unless you need to restrict by port.

* The OAuth2 filter config is essentially the same. We used a slightly different `redirect_path_matcher` (`/oauth2/callback` instead of `/_oauth2/callback`) as an example – you can choose the path. Just ensure consistency between `redirect_uri`, `redirect_path_matcher`, and the IdP’s allowed redirect URIs. In this example, if your service is accessed at `https://myapp.example.com`, the redirect URI would be `https://myapp.example.com/oauth2/callback`.

* The secrets (`token_secret` and `hmac_secret`) still refer to the same file paths. Because we mounted the secret into `/etc/istio/config` on the sidecar (via annotations), the same paths are valid.

* We included the same optional parameters (scopes, forward token, pass\_through\_matcher for health checks). These can be adjusted or omitted as needed.

Apply this EnvoyFilter in the `myapp-ns` namespace. It will patch the sidecar’s config for any pod matching the selector (it should pick up immediately for running pods; if not, reinject or restart the pod to be safe).

**Result:** Only requests to `myapp` will require OAuth login. If you access other services via the gateway, they won’t be intercepted by this filter (unless you also applied one at the gateway). When accessing `myapp`, the sidecar will redirect you to the IdP for login, then set cookies, etc., just as described for the gateway scenario. The user experience is similar; the difference is the OAuth2 flow is handled by the sidecar proxy instead of the gateway.

## 6. Validation and Best Practices

With everything in place, here are some final steps and tips to validate the setup and ensure a smooth operation:

* **Verify Envoy has loaded the filter:** Check the logs of the Envoy proxy (ingress gateway or sidecar) for any errors. A common mistake is not mounting the secrets correctly. If Envoy logs an error about missing `/etc/istio/config/token-secret.yaml` or `hmac-secret.yaml`, then the secret didn’t mount in the right place. Double-check the secret name, volume, and mount path. Also verify the secret data keys match the filenames.

* **Test the OAuth flow:** In a browser, access the application:

  1. You should be redirected to the OAuth provider’s login page.
  2. After login, you should be redirected back to your app’s URL. The page should load (or if your app relies on the token, it should detect the user).
  3. Check your browser cookies – you should see cookies like **BearerToken**, **OauthHMAC**, **OauthExpires**, etc., set by Envoy. The presence of these means the OAuth2 filter completed successfully and is maintaining your session.
  4. Refreshing the page or accessing another protected URL should not redirect again (until the token expires), indicating the session is recognized.
  5. Try hitting the health check URL (e.g. `/healthz/ready`) if you configured a pass-through. It should return normally (200 OK) without a redirect, even if you have no auth cookie, confirming that bypass works.
  6. (Optional) Test the sign-out: navigate to `/signout` (or whatever you set). The filter should clear the auth cookies (you might see them set with empty values or past expiry). After that, a subsequent request should trigger a fresh OAuth login redirect.

* **JWT validation (optional):** If you enabled `forward_bearer_token`, consider configuring an Istio `RequestAuthentication` with the JWT issuer and JWKS URI for your provider. This will insert Envoy’s JWT authN filter to validate the token’s signature and claims. By placing the OAuth2 filter before it, you get defense in depth – Envoy ensures the token is valid on every request (not just relying on cookie HMAC). You can then also use Istio `AuthorizationPolicy` to enforce roles/claims from the JWT if needed. This is not strictly required (the OAuth2 filter by itself ensures a valid login and uses the HMAC to prevent tampering), but it’s a good practice for zero-trust security.

* **Protecting multiple paths or hosts:** The examples above assume one set of OAuth settings for all paths on a host. If you need to exclude certain paths from auth, use `pass_through_matcher`. If you need different OAuth2 configs for different hosts or paths, you may need to create separate EnvoyFilters with appropriate conditions (for example, matching on listener filter chain by server name or using different workload selectors).

* **Secret rotation:** Plan how you will rotate the client secret or HMAC key. Because Envoy reads these secrets from files at startup (or when the listener is updated), updating the Kubernetes Secret alone does not live-reload the data in Envoy. You would need to trigger a reload – e.g., by restarting the pods or pushing a configuration change. One strategy is to update the secret (e.g., via new SDS file content) and then do a rolling restart of ingress gateway or relevant pods. Using GSM + an operator can help automate this. Always coordinate rotation of the client secret with updating it in your IdP’s registered application settings as well.

* **Security best practices:**

  * Limit the scopes and data you request from the IdP to only what you need (principle of least privilege).
  * Use secure cookies if possible (Envoy’s cookies for OAuth2 are HttpOnly and secure by default). They are tied to your domain.
  * Use HTTPS for all external redirects (as shown in our config with `https://` URLs).
  * Do not expose the callback or token exchange endpoints to the internet except via Envoy; those should only be triggered as part of the OAuth flow.
  * Monitor your Envoy logs for any OAuth flow errors (e.g., misconfigured redirect URIs, scope issues, token exchange failures). One common error with some providers is using incorrect scopes or endpoints – double check these if you see errors from the provider.

* **Troubleshooting tips:** If the flow isn’t working:

  * Use `istioctl proxy-config log` to bump Envoy logging to debug on the relevant proxy, specifically for the `oauth2` filter (`envoy.filters.http.oauth2`). This can provide insight into what’s happening (or not happening).
  * Ensure your cluster’s time is synced (OAuth tokens are time-sensitive; if your Envoy or system clock is skewed, you might see immediate expiry).
  * Ensure the OAuth client’s redirect URI exactly matches what Envoy is using (including path, and use of hostname vs. wildcard). A mismatch will cause the IdP to error or refuse the auth code.

By following this guide, you have configured Istio’s Envoy proxies to perform end-user authentication using OAuth2/OIDC, either at the ingress gateway or at individual service sidecars. This leverages Envoy’s native filter for OAuth2, providing a seamless login redirect and token management. Remember to keep your configuration and secrets up to date and secure. With proper validation and best practices, your Istio service mesh will now gate access to your apps with OAuth2, enhancing your security posture.

**Sources:**

* Istio documentation and community examples of EnvoyFilter usage for multiple contexts
* M. Strzelecki’s blog on OAuth2 filter in Istio (covers secret format and filter config)
* Okta developer forum discussion on Envoy OAuth2 config (example of Okta endpoints and JWT verification considerations)
* GitHub Istio issue discussions (user experiences with mounting secrets and filter errors)
