Похоже на сетевую аномалию, локальную именно для этой ноды (IRQ/softirq, offload/MTU, conntrack, kube-proxy/iptables или CNI datapath). Ниже — что проверять и как локализовать причину.

# 1) Что посмотреть в метриках (Prometheus/Grafana)

Сравниваем “проблемную ноду+под” с «нормальными» нодами/подами.

## Под (cAdvisor / kubelet)

* Входящие пакеты/байты/дропы/ошибки:
  `rate(container_network_receive_packets_total{pod="P",namespace="N"}[1m])`
  `rate(container_network_receive_bytes_total{pod="P",namespace="N"}[1m])`
  `rate(container_network_receive_packets_dropped_total{pod="P",namespace="N"}[1m])`
  `rate(container_network_receive_errors_total{pod="P",namespace="N"}[1m])`
* CPU throttling контейнера:
  `rate(container_cpu_cfs_throttled_seconds_total{pod="P"}[1m])` vs `rate(container_cpu_usage_seconds_total{pod="P"}[1m])`
* Если Istio/Envoy:
  `envoy_http_downstream_cx_active`, `envoy_http_downstream_rq_pending_overflow`, `envoy_server_overload_active`, `envoy_cluster_upstream_rq_retry`, гистограммы `*_rq_time`.

## Нода (node_exporter)

* Сетевые интерфейсы:
  `rate(node_network_receive_packets_total{device=~"^(eth|ens|enp).*"}[1m])`
  `rate(node_network_receive_drop_total{device=~"^(eth|ens|enp).*"}[1m])`
  `rate(node_network_receive_errs_total{device=~"^(eth|ens|enp).*"}[1m])`
* SoftIRQ/IRQ и нагрузка:
  `irate(node_softirq_total{softirq="NET_RX"}[1m])` по CPU
  `sum by (cpu)(irate(node_cpu_seconds_total{mode="softirq"}[1m]))`
  `sum by (cpu)(irate(node_cpu_seconds_total{mode="irq"}[1m]))`
* Conntrack:
  `node_nf_conntrack_entries`, `node_nf_conntrack_entries_limit`,
  `irate(node_netstat_IpExt_InNoRoutes[1m])`, `irate(node_netstat_Ip_Forwarding[1m])`
* Pressure/PSI (если включено):
  `avg_over_time(node_pressure_cpu_some[1m])`, `node_pressure_irq_full/some`

## kube-proxy / сервисы

* Если iptables-mode: степень раздутости правил:
  `kubeproxy_sync_proxy_rules_duration_seconds{quantile="0.99"}`
  `kubeproxy_network_programming_duration_seconds`
* IPVS-mode: `/proc/net/ip_vs_stats` через экспортер: `ipvs_inpkts`, `ipvs_outpkts`, `ipvs_conns`.

## DNS (если симптом “скачет” до десятков секунд)

* CoreDNS: `coredns_dns_request_count_total`/`coredns_dns_request_duration_seconds_bucket` + `coredns_cache_*`.

## CNI

* **Cilium**: `cilium_drop_count_total`, `cilium_forward_count_total`, `cilium_bpf_map_pressure`, `cilium_policy_*`.
* **Calico**: `felix_int_dataplane_*`, `felix_iptables_*`, `go_goroutines` (зависания), `felix_ipset_calls`.

# 2) Что сделать на проблемной НОДЕ (SSH/daemonset-debug)

Быстрые проверки “во время всплеска”.

**Системные счетчики**

```bash
# IRQ/SoftIRQ, NET_RX всплески?
watch -n1 'grep -E "NET_RX|HI|TIMER" /proc/softirqs | column -t'
watch -n1 'mpstat -P ALL 1 1'
watch -n1 'cat /proc/interrupts'
```

**NIC/драйвер**

```bash
IF=ens192   # ваш интерфейс
ethtool -S $IF | egrep 'rx_(errors|missed|no_buffer|dropped)|tx_(errors|dropped)'
ethtool -k $IF   # offload (GRO/LRO/TSO/GSO), сравнить с «здоровой» нодой
ethtool -g $IF   # RX/TX ring sizes
ethtool -c $IF   # coalesce
ethtool -l $IF   # RSS channels/queues
```

**Очереди / RPS/XPS / балансировка IRQ**

```bash
grep . /sys/class/net/$IF/queues/rx-*/rps_cpus
systemctl status irqbalance
```

**MTU/оверлей**

```bash
ip -d link show $IF
ip link show | egrep 'mtu|vxlan|geneve|flannel|cali|cilium'
# проверить, нет ли меньшего MTU только на этой ноде
```

**Conntrack**

```bash
sysctl net.netfilter.nf_conntrack_max
cat /proc/sys/net/netfilter/nf_conntrack_count
dmesg -T | egrep -i 'conntrack|nf_conntrack: table full'
conntrack -S   # require conntrack-tools
```

**Куда летят пакеты (быстрое выделение топ-говорящих)**

```bash
# если pod в netns: удобнее tcpdump через nsenter/ephemeral debug
tcpdump -i $IF -n -c 5000 -tttt -vv \
  '((broadcast or multicast) or arp or ip6) or host <POD_IP> or dst <POD_IP>' \
  -w /tmp/spike.pcap

# Быстрый взгляд без pcap:
tcpdump -i $IF -n 'host <POD_IP>' -l | awk '{print $3}' | cut -d. -f1-4 | sort | uniq -c | sort -nr | head
```

**Потери в qdisc/стеке**

```bash
tc -s qdisc show dev $IF
nstat -as | egrep 'InErrs|InDiscards|RcvbufErrors|OfoDrops|InCsumErrors'
ss -s
```

# 3) На что это похоже (гипотезы → как подтвердить/опровергнуть)

1. **SoftIRQ/IRQ saturation на ноде (NET_RX зашкаливает)**
   *Признаки:* всплеск `NET_RX`, `ksoftirqd/` грузит CPU, растут `rx_no_buffer`, дропы на qdisc.
   *Проверка:* `/proc/softirqs`, `ethtool -S`, `tc -s qdisc`.
   *Фикс:* включить/настроить RSS/RPS/XPS, увеличить RX-ring, поправить coalesce, включить `irqbalance`, пиновать IRQ по NUMA.

2. **MTU mismatch / фрагментация/black-hole на этой ноде**
   *Признаки:* именно на этой ноде длительные таймауты, много ретрансмитов, в pcap — ICMP Fragmentation needed/не приходит.
   *Проверка:* `ip -d link`, сверить MTU underlay/overlay с другими нодами; pcap.
   *Фикс:* привести MTU к единому (overlay MTU ~ underlay-50), отключить GSO/GRO для теста.

3. **Conntrack table full / hash-collisions**
   *Признаки:* `nf_conntrack: table full`, `conntrack -S` показывает drop, медленные новые подключения.
   *Проверка:* `nf_conntrack_count`≈`_max`, `dmesg`.
   *Фикс:* увеличить `nf_conntrack_max`/buckets, сократить idle-таймауты, уменьшить шумящий трафик.

4. **kube-proxy (iptables) разросся/зависает именно на этой ноде**
   *Признаки:* долгие `kubeproxy_sync_proxy_rules_*`, огромные таблицы iptables, длительная латентность DNAT.
   *Проверка:* метрики kube-proxy, `iptables -S | wc -l`, сравнить с другими нодами.
   *Фикс:* перейти на IPVS, почистить «мертвые» сервисы/ендпоинты, обновить kube-proxy.

5. **Flood broadcast/multicast/ARP/NDP, но виден только на этом сегменте**
   *Признаки:* в pcap много `ARP who-has`, mDNS/SSDP/LLDP, рост RX на ноде, а поду прилетает из-за hairpin/NAT.
   *Проверка:* `tcpdump '(broadcast or multicast) or arp'`, counters на свиче.
   *Фикс:* резать лишний L2-флуд (ACL), фильтровать mDNS/SSDP, чинить петли/STP.

6. **LB/Service конфигурация «прибила» трафик к ОДНОМУ поду/ноде (stickiness)**
   *Признаки:* sessionAffinity: ClientIP, externalTrafficPolicy: Local, один готовый endpoint. Всплеск pps именно в этот под.
   *Проверка:* `kubectl get svc -oyaml`, Endpoints/EndpointSlice; лог ingress/LB; `conntrack -L | grep <POD_IP>:<PORT> | wc -l`.
   *Фикс:* отключить stickiness, включить Local только где нужно, убедиться что реплики готовы на других нодах.

7. **Istio/Envoy локальная проблема (TLS rotate/xDS push/overload)**
   *Признаки:* во время всплеска метрики Envoy показывают overload, рост pending overflow, падает upstream success rate.
   *Проверка:* `istioctl pc metrics/logs/stats <pod>`, `server.overload_active`.
   *Фикс:* увеличить лимиты Envoy, проверить SDS/xDS, tune circuit breakers/connection pools.

8. **Driver-specific баг/offload на этой ноде**
   *Признаки:* только на одной ноде; отключение GRO/LRO/TSO и/или смена coalesce улучшает ситуацию.
   *Проверка:* `ethtool -k/-c`, сравнение с «хорошей» нодой.
   *Фикс:* harmonize offloads & coalesce, обновить драйвер/ядро/firmware.

9. **Queue starvation/NUMA misplacement**
   *Признаки:* один/пара CPU перегружены IRQ конкретного IF queue; остальное простаивает.
   *Проверка:* `/proc/interrupts` по RX-queue IRQ, `ethtool -l`, `rps_cpus`.
   *Фикс:* распределить IRQ по CPU, включить RPS/XPS, CPU pinning с учётом NUMA.

10. **DNS-шторм/ретраи → лавина запросов к поду**
    *Признаки:* latency скачет до десятков секунд; CoreDNS p99↑; tcpdump показывает волны однотипных коротких TCP/UDP.
    *Проверка:* CoreDNS метрики, pcap источников.
    *Фикс:* починить резолв/кэш, уменьшить ретраи, проверить search-suffix «взрывы».

# 4) Быстрые эксперименты (минимально инвазивные)

* **Переназначить под** на другую ноду (taint/cordon/drain) → подтвердить «узел-специфично».
* **Отключить на время** GRO/LRO на ноде: `ethtool -K $IF gro off lro off gso off tso off` → посмотреть, исчезают ли пики.
* **Временно увеличить conntrack_max** и RX-ring → проверка гипотез 1/3.
* **Снять pcap 30–60 сек во время пика** на host-IF и в netns пода — определить источники/порты/протокол.
* **Сравнить iptables/ipvs** объём и kube-proxy метрики с «здоровой» нодой.
* **Проверить MTU**: отправить ICMP “don’t fragment” на путь до пода крупным пакетом (`ping -M do -s 1472 …` с/без оверлея).

# 5) Если используете конкретные CNI/mesh

**Cilium**

```bash
cilium status
cilium metrics list | egrep 'drop|ct|bpf_map_pressure'
cilium monitor --from-pod N/P --type drop --type trace
cilium sysdump --output /tmp
```

**Calico**

```bash
calicoctl node status
calicoctl get ipPool -o wide
# felix metrics: iptables/ipset programming latency; посмотреть дропы интерфейсов vxlan/cali*
```

**Istio**

```bash
istioctl proxy-config metrics N/P
istioctl proxy-config clusters N/P --fqdn <upstream> -o json
# смотрим overload, retries, TLS/SDS события
```

# 6) Мини-чеклист «что принести на разбор»

1. Скрины 3–5 ключевых метрик с тайм-корреляцией: `NET_RX softirq`, RX drops/errs на ноде, `rx_packets`/`rx_dropped` пода, conntrack count, Envoy overload (если есть).
2. Вывод `ethtool -k/-S/-c/-l/-g`, `/proc/interrupts`, `tc -s qdisc`, `nf_conntrack_*`.
3. 30–60 сек pcap c host-IF и из netns пода во время пика.
4. `kubectl get svc/endpoints -oyaml` для сервисов, через которые идёт трафик к поду; настройки sessionAffinity / externalTrafficPolicy.
5. Сравнение MTU/офлоадов этой ноды с «нормальной».

Если нужно, могу дать точные one-liner’ы под ваш стек (например, как правильно попасть tcpdump’ом в netns контейнера через `kubectl debug`/`nsenter`) и помочь интерпретировать pcap/метрики.
