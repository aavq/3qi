***
***
***


# Установка Istio в кластер Kubernetes

Пререквизиты:
- Home Brew
- kubectl
- Кластер Kubernetes
- IP адрес, доступный с localhost который может быть использован как External-IP для Load Balancer Istio Ingress Gateway (опционально, если есть IP адрес для доступа к VM Lima с localhost)

Note: Если нет прав sudo или если не хочется создавать отдельно сеть для доступа к VM Lima по выделенному IP, то после установки Istio можно напрямую опубликовать порт 443 ingress gateway на localhot:8443 и использовать IP localhot для DNS записей

```bash
kubectl port-forward -n istio-system svc/istio-ingressgateway 8443:443 --address 0.0.0.0
```

1. Установка MetalLB (опционально, если есть IP адрес для доступа к VM Lima с localhost)

1.1 Запуск установки MetalLB без кастомизации

```bash
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.5/config/manifests/metallb-native.yaml
```
Note: Ожидаемый результат:
```log
namespace/metallb-system created
customresourcedefinition.apiextensions.k8s.io/bfdprofiles.metallb.io created
customresourcedefinition.apiextensions.k8s.io/bgpadvertisements.metallb.io created
customresourcedefinition.apiextensions.k8s.io/bgppeers.metallb.io created
customresourcedefinition.apiextensions.k8s.io/communities.metallb.io created
customresourcedefinition.apiextensions.k8s.io/ipaddresspools.metallb.io created
customresourcedefinition.apiextensions.k8s.io/l2advertisements.metallb.io created
customresourcedefinition.apiextensions.k8s.io/servicel2statuses.metallb.io created
serviceaccount/controller created
serviceaccount/speaker created
role.rbac.authorization.k8s.io/controller created
role.rbac.authorization.k8s.io/pod-lister created
clusterrole.rbac.authorization.k8s.io/metallb-system:controller created
clusterrole.rbac.authorization.k8s.io/metallb-system:speaker created
rolebinding.rbac.authorization.k8s.io/controller created
rolebinding.rbac.authorization.k8s.io/pod-lister created
clusterrolebinding.rbac.authorization.k8s.io/metallb-system:controller created
clusterrolebinding.rbac.authorization.k8s.io/metallb-system:speaker created
configmap/metallb-excludel2 created
secret/metallb-webhook-cert created
service/metallb-webhook-service created
deployment.apps/controller created
daemonset.apps/speaker created
validatingwebhookconfiguration.admissionregistration.k8s.io/metallb-webhook-configuration created
```

1.2 Проверяем что MetalLB запущен и Available
```bash
kubectl wait -n metallb-system deployment/controller --for=condition=Available --timeout=90s
```

Note: Ожидаемый результат:
```log
deployment.apps/controller condition met
```

2. Создаём пул IP адресов MetalLB состоящих из одного IP, полученного из сети Lima (опционально, если есть IP адрес для доступа к VM Lima с localhost)
   
2.1 Подготовим манифесты


```yaml
# cat 01-metallb.yaml
---
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: vm-pool-one-ip
  namespace: metallb-system
spec:
  addresses:
  - 192.168.105.4/32 # Has to be updated. /32 - means network IP range with only one IP
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: advert
  namespace: metallb-system
```

2.2 Применим манифесты 

```bash
kubectl apply -f 01-metallb.yaml
```

3. Установка Istio

3.1 Установка пакета istioctl через Home Brew

```bash
brew install istioctl
```


3.2 Подготовка манифеста для IstioOperator (опционально, если есть IP адрес для доступа к VM Lima с localhost)

```yaml
# cat 02-istio-lb.yaml
---
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: istiocontrolplane
  namespace: istio-system
spec:
  profile: demo
  components:
    ingressGateways:
    - name: istio-ingressgateway
      enabled: true
      k8s:
        service:
          type: LoadBalancer
          loadBalancerIP: 192.168.105.4 # Has to be updated.
```


3.3 Запуст установки Istio в кластере (необходимо выбрать один из возможных вариантов)

Если есть IP адрес для доступа к VM Lima с localhost и пункт 3.2 был выполнен:

```bash
istioctl install -f 02-istio-lb.yaml -y
```

Если нет IP адреса для доступа к VM Lima с localhost:

```bash
istioctl install --set profile=demo -y
```

3.4 Проверяем что Istio установлен

```bash
kubectl -n istio-system get svc istio-ingressgateway
```

Note: Ожидаемый результат:

Если есть IP адрес для доступа к VM Lima с localhost и пункт 3.2 был выполнен:

```log
NAME                   TYPE           CLUSTER-IP     EXTERNAL-IP     PORT(S)                                                                      AGE
istio-ingressgateway   LoadBalancer   10.108.4.180   192.168.105.4   15021:31040/TCP,80:30504/TCP,443:31440/TCP,31400:31438/TCP,15443:32541/TCP   11s
```


Если нет IP адреса для доступа к VM Lima с localhost:

```log
NAME                   TYPE           CLUSTER-IP      EXTERNAL-IP     PORT(S)                                                                      AGE
istio-ingressgateway   LoadBalancer   10.108.4.180    <none>          15021:31040/TCP,80:30504/TCP,443:31440/TCP,31400:31438/TCP,15443:32541/TCP   11s
```

Вот и всё. Istio установлен

***
***
***

