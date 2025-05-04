
***
***
***

Отказ от ответственности: для выполнения некоторых опциональных шагов, таких как создание сети для адресации к виртуальной машине напрямую по IP с localhost, могут потребоваться права суперпользователя. Из соображений безопасности, выполнение этой инструкции не рекомендуется на компьютерах, на которых есть доступ в корпоративную сеть.

ВАЖНО! Перечислить все пакеты и их версии, например версии: Home Brew, Lima, socket_vmnet, istioctl и т.д.

Запуск локального кластера Kubernetes в виртуальной машине Lima, установленной на MacOS.

1. Установка Lima

Пререквизиты:
- Home Brew
- kubectl
- Sudo Access (только в случае если нужно будет создавать виртуальную сеть, доступную с localhost)


1.1 Установим пакета Lima через Home Brew

```bash
brew install lima
```


1.2 Проверим, что Lima установлен и работает (опционально)

```bash
limactl start template://docker
```


Выберем: "Proceed with the current configuration" -> Нажимаем Enter
Ждём пока скачается образ и запустится VM c докер

```bash
limactl start template://docker
? Creating an instance "docker"  [Use arrows to move, type to filter]
> Proceed with the current configuration
  Open an editor to review or modify the current configuration
  Choose another template (docker, podman, archlinux, fedora, ...)
  Exit
```


1.3 Проверим, что VM запущена и работает (опционально)

```bash
brew install docker
```

```bash
docker context create lima-docker --docker "host=unix:///Users/qper/.lima/docker/sock/docker.sock"
```

Ожидаемый результат:
```bash
lima-docker
Successfully created context "lima-docker"
```

```bash
docker context use lima-docker
```
Ожидаемый результат:
```bash
lima-docker
Current context is now "lima-docker"
```

```bash
qper in ~ λ docker run hello-world
Unable to find image 'hello-world:latest' locally
latest: Pulling from library/hello-world
e6590344b1a5: Pull complete 
Digest: sha256:c41088499908a59aae84b0a49c70e86f4731e588a737f1637e73c8c09d995654
Status: Downloaded newer image for hello-world:latest

Hello from Docker!
This message shows that your installation appears to be working correctly.
...
```

1.4 Остановим VM с Docker (опционально)

```bash
limactl list
NAME      STATUS     SSH                VMTYPE    ARCH      CPUS    MEMORY    DISK      DIR
docker    Running    127.0.0.1:49873    vz        x86_64    4       4GiB      100GiB    ~/.lima/docker
```

```bash
limactl stop docker
INFO[0000] Sending SIGINT to hostagent process 7751     
INFO[0000] Waiting for the host agent and the driver processes to shut down 
INFO[0000] [hostagent] 2025/04/30 14:51:22 tcpproxy: for incoming conn 127.0.0.1:49877, error dialing "192.168.5.15:22": connect tcp 192.168.5.15:22: connection was refused 
INFO[0000] [hostagent] Received SIGINT, shutting down the host agent 
INFO[0000] [hostagent] Shutting down the host agent     
INFO[0000] [hostagent] Stopping forwarding "/run/user/501/docker.sock" (guest) to "/Users/qper/.lima/docker/sock/docker.sock" (host) 
INFO[0000] [hostagent] Shutting down VZ
...
```

| Note: Errors like the following may have occurred at this step:
| - "dhcp: unhandled message type: RELEASE" 
| - "accept tcp 127.0.0.1:49873: use of closed network connection"
| it expected.

1.5 Удалим VM с Docker (опционально)

```bash
 limactl delete docker 
INFO[0000] The vz driver process seems already stopped  
INFO[0000] The host agent process seems already stopped 
INFO[0000] Removing *.pid *.sock *.tmp under "/Users/qper/.lima/docker" 
INFO[0000] Removing "/Users/qper/.lima/docker/default_ep.sock" 
INFO[0000] Removing "/Users/qper/.lima/docker/default_fd.sock" 
INFO[0000] Removing "/Users/qper/.lima/docker/ha.sock"  
INFO[0000] Deleted "docker" ("/Users/qper/.lima/docker") 
```

2. Создание сети? (Опционально, нужно только в случае если нужно создавать IP адрес для LB кластера)

2.1 Установим пакета socket_vmnet через Home Brew

```bash
brew install socket_vmnet
```

2.2 По требованию Lima копия socket_vmnet должна быть установлена от имени root, для этого скопируем bin файл.


```bash
sudo mkdir -p /opt/socket_vmnet/bin
```

```bash
SRC=$(brew --prefix)/Cellar/socket_vmnet/$(brew list --versions socket_vmnet | awk '{print $2}')/bin/socket_vmnet
echo $SRC
# /usr/local/Cellar/socket_vmnet/1.2.1/bin/socket_vmnet
```

```bash
sudo install -o root -m 755 "$SRC" /opt/socket_vmnet/bin/socket_vmnet
```

```bash
limactl sudoers > etc_sudoers.d_lima && sudo install -o root etc_sudoers.d_lima "/private/etc/sudoers.d/lima"
```

2.3 Необходимо убедиться, что в настройках сети Lima параметр socketVMNet указывает на установленный bin socket_vmnet

```bash
cat ~/.lima/_config/networks.yaml | yq '.paths.socketVMNet'
/opt/socket_vmnet/bin/socket_vmnet
```


3. Запуск локального кластера Kubernetes

3.1 Запустим VM с кластером из шаблона k8s

В случае если шаг 2 был пропущен:

```bash
limactl start --name k8s template://k8s
```

В случае если шаг 2 был выполнен:

```bash
limactl start --name k8s --network=lima:shared template://k8s
```


3.2 Проверим что VM с кластером запустилась (опционально)

```bash
limactl list
NAME    STATUS     SSH                VMTYPE    ARCH      CPUS    MEMORY    DISK      DIR
k8s     Running    127.0.0.1:50052    vz        x86_64    4       4GiB      100GiB    ~/.lima/k8s
```


3.3 Установим значение Kube Config соответствующее kubeconfig кластера в Lima
```bash
export KUBECONFIG="${HOME}/.lima/k8s/copied-from-guest/kubeconfig.yaml"
```

3.4 Убедимся что API кластера доступен (опционально)

```bash
kubectl get ns
NAME                 STATUS   AGE
default              Active   11s
kube-flannel         Active   11s
kube-node-lease      Active   11s
kube-public          Active   11s
kube-system          Active   11s
```

4. Проверяем какой IP получила VM в сети, созданной на этапе номер 2.??? (опционально, если сеть была создана на этапе 2)

4.1 Смотрим все сетевые интерфейсы IPv4

```bash
limactl shell k8s ip -4 addr show scope global
```

Note: Ожидаемый результат:

```log
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    inet 192.168.5.15/24 metric 200 brd 192.168.5.255 scope global dynamic eth0
       valid_lft 2955sec preferred_lft 2955sec
3: lima0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    inet 192.168.105.4/24 metric 100 brd 192.168.105.255 scope global dynamic lima0
       valid_lft 2955sec preferred_lft 2955sec
4: flannel.1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 qdisc noqueue state UNKNOWN group default 
    inet 10.244.0.0/32 scope global flannel.1
       valid_lft forever preferred_lft forever
5: cni0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 qdisc noqueue state UP group default qlen 1000
    inet 10.244.0.1/24 brd 10.244.0.255 scope global cni0
       valid_lft forever preferred_lft forever
```

4.2 Смотрим IPv4 сетевыго интерфейса lima0

```bash
limactl shell k8s -- ip -4 addr show dev lima0 |grep -oE 'inet\s+[0-9.]+'
```

Note: Ожидаемый результат:

```log
inet 192.168.105.4
```

4.3 Проверяем доступность VM с использованием этого IPv4


```bash
nc -zv 192.168.105.4 22
```

Note: Ожидаемый результат:

```log
Connection to 192.168.105.4 port 22 [tcp/ssh] succeeded!
```

Или

```bash
ping -c 4 192.168.105.4
```

Note: Ожидаемый результат:

```log
PING 192.168.105.4 (192.168.105.4): 56 data bytes
64 bytes from 192.168.105.4: icmp_seq=0 ttl=64 time=0.639 ms
64 bytes from 192.168.105.4: icmp_seq=1 ttl=64 time=1.229 ms
64 bytes from 192.168.105.4: icmp_seq=2 ttl=64 time=0.468 ms
64 bytes from 192.168.105.4: icmp_seq=3 ttl=64 time=0.490 ms

--- 192.168.105.4 ping statistics ---
4 packets transmitted, 4 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 0.468/0.707/1.229/0.309 ms
```

Всё кластер создан.
Так же, если выполнены успешно шаги 2 и 4, то ещё и создана сеть, доступная с localhost, а VM K8S получила IP в этой сети.
