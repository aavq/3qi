```bash

kubectl logs httpbin-5b6fb5894b-cxh9g -c istio-proxy
2025-04-16T18:06:17.864280Z	info	FLAG: --concurrency="0"
2025-04-16T18:06:17.864343Z	info	FLAG: --domain="default.svc.cluster.local"
2025-04-16T18:06:17.864350Z	info	FLAG: --help="false"
2025-04-16T18:06:17.864353Z	info	FLAG: --log_as_json="false"
2025-04-16T18:06:17.864355Z	info	FLAG: --log_caller=""
2025-04-16T18:06:17.864357Z	info	FLAG: --log_output_level="default:info"
2025-04-16T18:06:17.864358Z	info	FLAG: --log_stacktrace_level="default:none"
2025-04-16T18:06:17.864372Z	info	FLAG: --log_target="[stdout]"
2025-04-16T18:06:17.864375Z	info	FLAG: --meshConfig="./etc/istio/config/mesh"
2025-04-16T18:06:17.864376Z	info	FLAG: --outlierLogPath=""
2025-04-16T18:06:17.864378Z	info	FLAG: --profiling="true"
2025-04-16T18:06:17.864380Z	info	FLAG: --proxyComponentLogLevel="misc:error"
2025-04-16T18:06:17.864382Z	info	FLAG: --proxyLogLevel="warning"
2025-04-16T18:06:17.864384Z	info	FLAG: --serviceCluster="istio-proxy"
2025-04-16T18:06:17.864386Z	info	FLAG: --stsPort="0"
2025-04-16T18:06:17.864388Z	info	FLAG: --templateFile=""
2025-04-16T18:06:17.864389Z	info	FLAG: --tokenManagerPlugin=""
2025-04-16T18:06:17.864392Z	info	FLAG: --vklog="0"
2025-04-16T18:06:17.864394Z	info	Version 1.25.2-0d83506c28834f5f12553ee11d76a18e7ea75f20-Clean
2025-04-16T18:06:17.864400Z	info	Set max file descriptors (ulimit -n) to: 524288
2025-04-16T18:06:17.864569Z	info	Proxy role	ips=[10.244.0.92] type=sidecar id=httpbin-5b6fb5894b-cxh9g.default domain=default.svc.cluster.local
2025-04-16T18:06:17.864778Z	info	Apply proxy config from env {}

2025-04-16T18:06:17.866586Z	info	cpu limit detected as 2, setting concurrency
2025-04-16T18:06:17.866851Z	info	Effective config: binaryPath: /usr/local/bin/envoy
concurrency: 2
configPath: ./etc/istio/proxy
controlPlaneAuthPolicy: MUTUAL_TLS
discoveryAddress: istiod.istio-system.svc:15012
drainDuration: 45s
proxyAdminPort: 15000
serviceCluster: istio-proxy
statNameLength: 189
statusPort: 15020
terminationDrainDuration: 5s

2025-04-16T18:06:17.866892Z	info	JWT policy is third-party-jwt
2025-04-16T18:06:17.866974Z	info	using credential fetcher of JWT type in cluster.local trust domain
2025-04-16T18:06:17.869760Z	info	Starting default Istio SDS Server
2025-04-16T18:06:17.869972Z	info	CA Endpoint istiod.istio-system.svc:15012, provider Citadel
2025-04-16T18:06:17.870096Z	info	Using CA istiod.istio-system.svc:15012 cert with certs: var/run/secrets/istio/root-cert.pem
2025-04-16T18:06:17.869755Z	info	Opening status port 15020
2025-04-16T18:06:17.872539Z	info	xdsproxy	Initializing with upstream address "istiod.istio-system.svc:15012" and cluster "Kubernetes"
2025-04-16T18:06:17.875518Z	info	Pilot SAN: [istiod.istio-system.svc]
2025-04-16T18:06:17.877227Z	info	Starting proxy agent
2025-04-16T18:06:17.877316Z	info	Envoy command: [-c etc/istio/proxy/envoy-rev.json --drain-time-s 45 --drain-strategy immediate --local-address-ip-version v4 --file-flush-interval-msec 1000 --disable-hot-restart --allow-unknown-static-fields -l warning --component-log-level misc:error --skip-deprecated-logs --concurrency 2]
2025-04-16T18:06:17.887759Z	info	sds	Starting SDS grpc server
2025-04-16T18:06:17.887917Z	info	sds	Starting SDS server for workload certificates, will listen on "var/run/secrets/workload-spiffe-uds/socket"
2025-04-16T18:06:17.944207Z	warning	envoy main external/envoy/source/server/server.cc:863	Usage of the deprecated runtime key overload.global_downstream_max_connections, consider switching to `envoy.resource_monitors.global_downstream_max_connections` instead.This runtime key will be removed in future.thread=14
2025-04-16T18:06:17.945205Z	warning	envoy main external/envoy/source/server/server.cc:959	There is no configured limit to the number of allowed active downstream connections. Configure a limit in `envoy.resource_monitors.global_downstream_max_connections` resource monitor.	thread=14
2025-04-16T18:06:17.953088Z	info	xdsproxy	connected to delta upstream XDS server: istiod.istio-system.svc:15012	id=1
2025-04-16T18:06:17.974228Z	info	ads	ADS: new connection for node:1
2025-04-16T18:06:17.974647Z	info	cache	generated new workload certificate	resourceName=default latency=99.036203ms ttl=23h59m59.025357866s
2025-04-16T18:06:17.974689Z	info	cache	Root cert has changed, start rotating root cert
2025-04-16T18:06:17.974746Z	info	cache	returned workload trust anchor from cache	ttl=23h59m59.025254552s
2025-04-16T18:06:17.974775Z	info	cache	returned workload certificate from cache	ttl=23h59m59.025225734s
2025-04-16T18:06:17.975820Z	info	ads	ADS: new connection for node:2
2025-04-16T18:06:17.976000Z	info	cache	returned workload trust anchor from cache	ttl=23h59m59.024002485s
2025-04-16T18:06:18.013147Z	warning	envoy config external/envoy/source/extensions/config_subscription/grpc/delta_subscription_state.cc:296	delta config for type.googleapis.com/envoy.config.listener.v3.Listener rejected: Error adding/updating listener(s) virtualInbound: Proto constraint validation failed (OAuth2ValidationError.Config: embedded message failed validation | caused by OAuth2ConfigValidationError.Credentials: embedded message failed validation | caused by field: "token_formation", reason: is required): config {
  token_endpoint {
    uri: "http://keycloak.default.svc.cluster.local/realms/demo-realm/protocol/openid-connect/token"
    cluster: "outbound|80||keycloak.default.svc.cluster.local"
    timeout {
      seconds: 5
    }
  }
  authorization_endpoint: "http://keycloak.default.svc.cluster.local/realms/demo-realm/protocol/openid-connect/auth/"
  credentials {
    client_id: "test-client"
    token_secret {
      name: "oauth2-client-secret"
    }
  }
  redirect_uri: "http://httpbin.local:8080/get"
  forward_bearer_token: true
  auth_scopes: "user"
  auth_scopes: "openid"
  auth_scopes: "email"
  resources: "oauth2-resource"
}

	thread=14
2025-04-16T18:06:18.013199Z	warning	envoy config external/envoy/source/extensions/config_subscription/grpc/grpc_subscription_impl.cc:138	gRPC config for type.googleapis.com/envoy.config.listener.v3.Listener rejected: Error adding/updating listener(s) virtualInbound: Proto constraint validation failed (OAuth2ValidationError.Config: embedded message failed validation | caused by OAuth2ConfigValidationError.Credentials: embedded message failed validation | caused by field: "token_formation", reason: is required): config {
  token_endpoint {
    uri: "http://keycloak.default.svc.cluster.local/realms/demo-realm/protocol/openid-connect/token"
    cluster: "outbound|80||keycloak.default.svc.cluster.local"
    timeout {
      seconds: 5
    }
  }
  authorization_endpoint: "http://keycloak.default.svc.cluster.local/realms/demo-realm/protocol/openid-connect/auth/"
  credentials {
    client_id: "test-client"
    token_secret {
      name: "oauth2-client-secret"
    }
  }
  redirect_uri: "http://httpbin.local:8080/get"
  forward_bearer_token: true
  auth_scopes: "user"
  auth_scopes: "openid"
  auth_scopes: "email"
  resources: "oauth2-resource"
}

	thread=14
2025-04-16T18:06:19.488430Z	warn	Envoy proxy is NOT ready: config received from XDS server, but was rejected: cds updates: 1 successful, 0 rejected; lds updates: 0 successful, 1 rejected
2025-04-16T18:06:20.486246Z	warn	Envoy proxy is NOT ready: config received from XDS server, but was rejected: cds updates: 1 successful, 0 rejected; lds updates: 0 successful, 1 rejected
2025-04-16T18:06:21.487608Z	warn	Envoy proxy is NOT ready: config received from XDS server, but was rejected: cds updates: 1 successful, 0 rejected; lds updates: 0 successful, 1 rejected


```
