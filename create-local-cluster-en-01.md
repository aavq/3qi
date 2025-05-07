# Install local isolated K8S Cluster

## Quick summary

On macOS 14+ you can:

1. Install Homebrew 4.5.1.
2. Install **Lima**, **kubectl**, **yq** and other CLI tools with Homebrew.
3. (Optionally) Create a routable `lima:shared` network using the root‑owned **socket\_vmnet** 1.2.1 binary.
4. Launch the **k8s template** that ships Kubernetes 1.33.0. 
5. Export the generated `kubeconfig`, test `kubectl`,

And you are ready to develop or demo workloads locally - while keeping the whole stack isolated enough to delete and re‑create in seconds.

---

## 0.  Exact package versions

| Component                   | Version (verified 2025‑05‑07)       |
| --------------------------- | ----------------------------------- |
| Homebrew (`brew`)           | **4.5.1** ([GitHub][1])             |
| Lima (`limactl`)            | **1.0.7** ([GitHub][2])             |
| socket\_vmnet               | **1.2.1** ([GitHub][7])             |
| Docker CLI (optional)       | **28.1.1** ([Homebrew Formulae][3]) |
| Kubernetes CLI (`kubectl`)  | **1.33.0** ([Homebrew Formulae][4]) |
| Cluster template Kubernetes | **1.33.0** ([Kubernetes][5])        |
| yq                          | **4.45.2** ([Homebrew Formulae][6]) |

---

## 1.  Prerequisites

1. **macOS 14 or newer** with Apple Silicon or Intel VT‑x.
2. **Xcode Command‑Line Tools** (`xcode-select --install`).
3. **Administrator account** for the some of `sudo` lines required by `socket_vmnet`.
4. **Homebrew 4.5.1** or newer:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   brew update && brew upgrade # keeps all bottles current
   ```

   Homebrew tags 4.5.1 as the latest stable release as of 7 May 2025. ([GitHub][1])

---

## 2.  Install core CLI tools

```bash
brew install lima kubernetes-cli yq
```

The formulae deliver Lima 1.0.7, kubectl 1.33.0, and yq 4.45.2 out of the box. ([GitHub][2], [Homebrew Formulae][4], [Homebrew Formulae][6])
Verify:

```bash
limactl --version         # limactl version 1.0.7
kubectl version --client  # v1.33.0
yq --version              # yq (https://github.com/mikefarah/yq/) version 4.45.2
```

---

## 3.  (Optional) Enable a routable VM network with socket\_vmnet

> **Security note:** the binary **must be owned by root**; Lima refuses to start in shared mode if the file is writable by normal users. ([GitHub][8])

### 3.1 Install and harden the binary

```bash
brew install socket_vmnet
sudo mkdir -p /opt/socket_vmnet/bin
sudo install -o root -m 755 \
  "$(brew --prefix)/opt/socket_vmnet/bin/socket_vmnet" \
  /opt/socket_vmnet/bin/socket_vmnet
```

### 3.2 Add Lima’s sudoers snippet

```bash
limactl sudoers > etc_sudoers.d_lima
sudo install -o root etc_sudoers.d_lima /private/etc/sudoers.d/lima
rm etc_sudoers.d_lima
```

### 3.3 Confirm Lima detects the binary

```bash
yq '.paths.socketVMNet' ~/.lima/_config/networks.yaml
# => /opt/socket_vmnet/bin/socket_vmnet
```

---

## 4.  Launch the Kubernetes VM

```bash
# With routable IP (requires step 3)
limactl start --name k8s --network=lima:shared template://k8s
# Without extra networking
# limactl start --name k8s template://k8s
```

The README shows the same two‑line pattern for any Lima template. ([GitHub][9])

Check status:

```bash
limactl list
```

---

## 5.  Export and test your kubeconfig

```bash
export KUBECONFIG="$HOME/.lima/k8s/copied-from-guest/kubeconfig.yaml"
kubectl get nodes        # should list a single Ready node running VERSION is v1.33.0
```

Kubernetes 1.33.0 became the latest stable on 7 May 2025. ([Kubernetes][5])

---

## 6.  (If you enabled the shared network) confirm the VM IP

6.1 **Discover the `lima0` address**

   ```bash
   limactl shell k8s -- ip -4 addr show dev lima0 | grep -oE 'inet\s+[0-9.]+' | awk '{print $2}'
   # e.g. 192.168.105.4
   ```

   The pool of IPs for shared mode has to be `192.168.105.x` ([GitHub][10])

6.2 **Ping or SSH probe**

   ```bash
   ping -c 3 192.168.105.4
   # PING 192.168.105.4 (192.168.105.4): 56 data bytes
   # 64 bytes from 192.168.105.4: icmp_seq=0 ttl=64 time=0.618 ms
   # 64 bytes from 192.168.105.4: icmp_seq=1 ttl=64 time=0.797 ms
   # 64 bytes from 192.168.105.4: icmp_seq=2 ttl=64 time=0.788 ms
   nc -zv 192.168.105.4 22
   # Connection to 192.168.105.4 port 22 [tcp/ssh] succeeded!
   ```

A successful reply proves that `socket_vmnet` is working and the VM is reachable from `localhost`.

---

## 7.  Clean shutdown & teardown

```bash
limactl stop k8s # graceful shutdown
# limactl delete k8s - (irreversible) removes disk image and metadata. Only in the case when all required experiments have been completed
```

The same commands work for any extra template VM such as `docker`. ([GitHub][9])

---

## 8.  Troubleshooting cheat‑sheet

| Symptom                                                 | Probable cause                    | Fix                                                                                         |
| ------------------------------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------- |
| `paths.socketVMNet` points to a user‑writable directory | insecure binary                   | move it to `/opt/socket_vmnet/bin` and chown root. ([GitHub][8])                            |
| VM stuck in **Starting**                                | macOS firewall blocks DHCP/bootpd | Allow the `socket_vmnet` helper through macOS Firewall or temporarily disable the firewall. |
| `kubectl get nodes` shows `NotReady` after >5 min       | container images still pulling    | `kubectl get po -A -w` to check images have been pulled and all pods are redy               |

---

### The importan things

* **Pinned versions** guarantee that everyone can reproduces the environment - even months later - without "it works on my laptop" surprises.
* **Root‑only `socket_vmnet`** prevents interception of privileged paths.
* **Template VMs** this means you can experiment in seconds; there is no lingering state.
* **Optional networking** keeps default installs minimal yet offers full Layer‑3 reachability when you need a LoadBalancer IP or cross‑VM traffic.

Let's keep creating a cluster environment!

[1]: https://github.com/Homebrew/brew/releases "Releases - Homebrew/brew - GitHub"
[2]: https://github.com/lima-vm/lima/releases "Releases - lima-vm/lima - GitHub"
[3]: https://formulae.brew.sh/formula/docker?utm_source=chatgpt.com "docker - Homebrew Formulae"
[4]: https://formulae.brew.sh/formula/kubernetes-cli "kubernetes-cli  -  Homebrew Formulae"
[5]: https://kubernetes.io/releases/ "Releases | Kubernetes"
[6]: https://formulae.brew.sh/formula/yq?utm_source=chatgpt.com "yq - Homebrew Formulae"
[7]: https://github.com/lima-vm/socket_vmnet/releases "vmnet.framework support for unmodified rootless QEMU v1.2.1"
[8]: https://github.com/lima-vm/socket_vmnet?utm_source=chatgpt.com "lima-vm/socket_vmnet: vmnet.framework support for ... - GitHub"
[9]: https://github.com/lima-vm/lima "GitHub - lima-vm/lima: Linux virtual machines, with a focus on running containers"
[10]: https://github.com/lima-vm/lima/issues/1259?utm_source=chatgpt.com "shared network mode not working on Mac M1 - Issue #1259 - lima ..."
[11]: https://istio.io/latest/news/releases/1.25.x/announcing-1.25.2/?utm_source=chatgpt.com "Announcing Istio 1.25.2"
