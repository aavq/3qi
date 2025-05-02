
***
***
***

1. Установка cert-manager


Пререквизиты:
- kubectl
- Sudo Access (только в случае если нужно будет добавлять корневой сертификат CA в доверительные на localhost)

1.1 Установим CRDS для cert-manager

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.1/cert-manager.crds.yaml
```


1.2 Установим cert-manager

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.1/cert-manager.yaml
```

1.3 Убеждаемся что STATUS всех Pods - Running

```bash
kubectl -n cert-manager get pods
```

1.4 Создаём корневой сертификат

```yaml
# issuer-root.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-root
spec:
  selfSigned: {}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: my-root-ca
  namespace: cert-manager
spec:
  isCA: true
  commonName: "my‑root"
  secretName: my-root-ca-secret
  duration: 87600h
  issuerRef:
    name: selfsigned-root
    kind: ClusterIssuer
```

```bash
kubectl apply -f issuer-root.yaml
```

1.5. Создаем CA Issuer, который будет подписывать сервисные сертификаты

```yaml
# ca-issuer.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: my-ca-issuer
spec:
  ca:
    secretName: my-root-ca-secret
```

1.6 Запрашиваем создание тестового сертификата в namespace istio-system

```yaml
# httpbin-cert.yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: httpbin-cert
  namespace: istio-system
spec:
  secretName: httpbin-tls
  commonName: httpbin.lima
  dnsNames:
  - httpbin.lima
  issuerRef:
    name: my-ca-issuer
    kind: ClusterIssuer
```

READY должен быть True

```bash
kubectl -n istio-system get certificates.cert-manager.io httpbin-cert
NAME           READY   SECRET        AGE
httpbin-cert   True    httpbin-tls   11s
```

А вот и секрет для нашего сертификата

```bash
kubectl -n istio-system get secrets httpbin-tls 
NAME          TYPE                DATA   AGE
httpbin-tls   kubernetes.io/tls   3      11s
```

 

1.7 Добавлять корневой сертификат CA cert-manager в доверительные на localhost

```bash
kubectl get secret my-root-ca-secret -n cert-manager -o jsonpath='{.data.ca\.crt}' | base64 -d > root.crt
```

```bash
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain root.crt
```

Отлично cert-manager установлен выпускает сертификаты по запросу. А так же, если шаг 1.7 был выполнен, то наш localhost доверяет подписанным СА сертификатам


***
***
***
