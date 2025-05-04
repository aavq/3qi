

Note: Для устновки Keycloak в конфигурации с сохранением состояния, требуется база данных, например PostgreSQL. По умолчанию эта база данных устанавливается из того же helm chart keycloak, но для её установки требуется Persisten Volume а следовательно Storage Classes должен быть создан в кластере. Самый простой способ - использовать локальное хранилице storage class - local-path.

1. Установим Storage Class

1.1 Установим Storage Class local-path из репозитория Rancher

```bash
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/master/deploy/local-path-storage.yaml
```

1.2 Проверим что Storage Class создался

```bash
kubectl get storageclasses.storage.k8s.io
NAME                   PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
local-path             rancher.io/local-path   Delete          WaitForFirstConsumer   false                  11s
```


1.3 Необходимо установить этот Storage Class как Storage Class по умолчанию для обработки PVC

```bash
kubectl patch storageclass local-path \\n  -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```


1.4 Проверим что Storage Class выбран как default
```bash
kubectl get storageclasses.storage.k8s.io
NAME                   PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
local-path (default)   rancher.io/local-path   Delete          WaitForFirstConsumer   false                  18s
```


2. Подготовка к установке Keycloak


```bash
brew install helm
```


2.1 Добавим Helm repository, содержащий Helm Chart Keycloak и обновим индексы репозиториев

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami || true && helm repo update
```

2.2 Убедимся что Helm Chart Keycloak доступен в репозитории

```bash
helm search repo bitnami/keycloak
NAME            	CHART VERSION	APP VERSION	DESCRIPTION                                       
bitnami/keycloak	24.6.1       	26.2.1     	Keycloak is a high performance Java-based ident...
```

2.3 Создадим пространство имён для keycloak

```bash
kubectl create ns keycloak
```

2.4 Включим istio injection в пространстве имён keycloak

```bash
kubectl label ns keycloak istio-injection=enabled
```

2.5 Создадим файл values-override.yaml, в котором будем переопределять значения установленные по умолчанию в Helm Chart Keycloak

```yaml
# 07-keycloak-values-override.yaml
---
auth:
  adminUser: admin
  adminPassword: AdminP@ssw0rd

hostname:
  url: https://idp.lima
  adminUrl: https://idp.lima
  strict: true

proxy: edge
proxyAddressForwarding: true

extraEnvVars:
  - name: KC_HTTP_ENABLED
    value: "true"

service:
  type: ClusterIP
ingress:
  enabled: false
```


3. Установка Keycloak

3.1 Установим Keycloak как helm релиз, переопределив некоторые значения через файл values-override.yaml

```bash
helm upgrade --install keycloak bitnami/keycloak --namespace keycloak -f 07-keycloak-values-override.yaml
```

3.2 Убедимся что все поды в статусе 

```bash
kubectl -n keycloak get po
NAME                    READY   STATUS    RESTARTS         AGE
keycloak-0              2/2     Running    0               11s
keycloak-postgresql-0   2/2     Running    0               11s
```

3.3 Проверим, какой порт "слушает" сервис keycloak

```bash
kubectl -n keycloak get svc keycloak
NAME       TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)   AGE
keycloak   ClusterIP   10.106.43.176   <none>        80/TCP    18s
```


3.4 Создадим сертификат для доменного имени idp.lima

```yaml
# certificate-idp-lima.yaml
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: idp-lima
  namespace: keycloak
spec:
  secretName: idp-lima-tls
  issuerRef:
    kind: ClusterIssuer
    name: my-ca-issuer
  commonName: idp.lima
  dnsNames:
  - idp.lima
```

```bash
kubectl apply -f certificate-idp-lima.yaml
```

3.5 Создадим Gateway и VirtualService
```yaml
# gateway-keycloak-gateway.yaml
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: keycloak-gateway
  namespace: keycloak
spec:
  selector:
    istio: ingressgateway
  servers:
  - port:
      number: 443
      name: https
      protocol: HTTPS
    hosts:
    - idp.lima
    tls:
      mode: SIMPLE
      credentialName: idp-lima-tls

```

```bash
kubectl apply -f gateway-keycloak-gateway.yaml
```


```yaml
---
# virtualservice-keycloak.yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: keycloak
  namespace: keycloak
spec:
  hosts:
  - idp.lima
  gateways:
  - keycloak-gateway
  http:
  - match:
    - uri:
        prefix: /
    route:
    - destination:
        host: keycloak.keycloak.svc.cluster.local
        port:
          number: 80
```


```bash
kubectl apply -f virtualservice-keycloak.yaml
```

3.6 Создадим DNS запись созданного IdP на localhost (опционально)

```bash
echo "192.168.105.4  idp.lima" | sudo tee -a /etc/hosts
```

```bash
curl -k https://idp.lima/auth \
  --resolve idp.lima:443:192.168.105.4 \
  -I
```

3.7 Добавим запись в configmap coredns

```bash
kubectl -n kube-system edit configmap coredns
```

```json
        hosts {
            192.168.105.4 idp.lima
            fallthrough
        }
```

3.8 Перезапустим coredns


```bash
kubectl -n kube-system rollout restart deployment coredns
```

3.9 Проверим доступность IdP по имени в кластере

```bash
kubectl run test -it --rm --image busybox:1.36 --restart=Never -- nslookup idp.lima
```

***
***
***
