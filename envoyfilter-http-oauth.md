

```yaml
# k get envoyfilters.networking.istio.io -oyaml
apiVersion: v1
items:
- apiVersion: networking.istio.io/v1alpha3
  kind: EnvoyFilter
  metadata:
    annotations:
      kubectl.kubernetes.io/last-applied-configuration: |
        {"apiVersion":"networking.istio.io/v1alpha3","kind":"EnvoyFilter","metadata":{"annotations":{},"name":"httpbin-oauth","namespace":"default"},"spec":{"configPatches":[{"applyTo":"HTTP_FILTER","match":{"context":"SIDECAR_INBOUND","listener":{"filterChain":{"filter":{"name":"envoy.filters.network.http_connection_manager","subFilter":{"name":"envoy.filters.http.router"}}}}},"patch":{"operation":"INSERT_BEFORE","value":{"name":"envoy.filters.http.oauth2","typed_config":{"@type":"type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2","config":{"authorization_endpoint":"https://idp.example.com/auth/realms/demo/protocol/openid-connect/auth","credentials":{"client_id":"httpbin-frontend","cookie_domain":".lima","cookie_names":{"bearer_token":"BearerToken","oauth_expires":"OauthExpires","oauth_hmac":"OauthHMAC"},"hmac_secret":{"name":"idp-hmac","sds_config":{"path":"/etc/istio/creds/hmac-secret.yaml"}},"token_secret":{"name":"idp-token","sds_config":{"path":"/etc/istio/creds/token-secret.yaml"}}},"forward_bearer_token":true,"redirect_path_matcher":{"path":{"exact":"/oauth2/callback"}},"redirect_uri":"%REQ(x-forwarded-proto)%://%REQ(:authority)%/oauth2/callback","signout_path":{"path":{"exact":"/logout"}},"token_endpoint":{"cluster":"idp-oauth-cluster","timeout":"5s","uri":"https://idp.example.com/auth/realms/demo/protocol/openid-connect/token"},"use_refresh_token":true}}}}},{"applyTo":"CLUSTER","patch":{"operation":"ADD","value":{"connect_timeout":"10s","dns_lookup_family":"V4_ONLY","load_assignment":{"cluster_name":"idp-oauth-cluster","endpoints":[{"lb_endpoints":[{"endpoint":{"address":{"socket_address":{"address":"idp.example.com","port_value":443}}}}]}]},"name":"idp-oauth-cluster","transport_socket":{"name":"envoy.transport_sockets.tls","typed_config":{"@type":"type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext","sni":"idp.example.com"}},"type":"LOGICAL_DNS"}}}],"workloadSelector":{"labels":{"app":"http-bin"}}}}
    creationTimestamp: "2025-04-19T15:25:17Z"
    generation: 1
    name: httpbin-oauth
    namespace: default
    resourceVersion: "33112"
    uid: 21c1e211-33a1-45a0-9f46-3a6d3560bfe5
  spec:
    configPatches:
    - applyTo: HTTP_FILTER
      match:
        context: SIDECAR_INBOUND
        listener:
          filterChain:
            filter:
              name: envoy.filters.network.http_connection_manager
              subFilter:
                name: envoy.filters.http.router
      patch:
        operation: INSERT_BEFORE
        value:
          name: envoy.filters.http.oauth2
          typed_config:
            '@type': type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
            config:
              authorization_endpoint: https://idp.example.com/auth/realms/demo/protocol/openid-connect/auth
              credentials:
                client_id: httpbin-frontend
                cookie_domain: .lima
                cookie_names:
                  bearer_token: BearerToken
                  oauth_expires: OauthExpires
                  oauth_hmac: OauthHMAC
                hmac_secret:
                  name: idp-hmac
                  sds_config:
                    path: /etc/istio/creds/hmac-secret.yaml
                token_secret:
                  name: idp-token
                  sds_config:
                    path: /etc/istio/creds/token-secret.yaml
              forward_bearer_token: true
              redirect_path_matcher:
                path:
                  exact: /oauth2/callback
              redirect_uri: '%REQ(x-forwarded-proto)%://%REQ(:authority)%/oauth2/callback'
              signout_path:
                path:
                  exact: /logout
              token_endpoint:
                cluster: idp-oauth-cluster
                timeout: 5s
                uri: https://idp.example.com/auth/realms/demo/protocol/openid-connect/token
              use_refresh_token: true
    - applyTo: CLUSTER
      patch:
        operation: ADD
        value:
          connect_timeout: 10s
          dns_lookup_family: V4_ONLY
          load_assignment:
            cluster_name: idp-oauth-cluster
            endpoints:
            - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: idp.example.com
                      port_value: 443
          name: idp-oauth-cluster
          transport_socket:
            name: envoy.transport_sockets.tls
            typed_config:
              '@type': type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
              sni: idp.example.com
          type: LOGICAL_DNS
    workloadSelector:
      labels:
        app: http-bin
kind: List
metadata:
  resourceVersion: ""
```
