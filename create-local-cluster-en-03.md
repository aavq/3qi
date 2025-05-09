Below is a clean-room, **corporate-friendly** run-book for deploying `cert-manager v1.17.1` in an existing Kubernetes cluster and issuing a test TLS certificate that your local macOS host can trust.  All tooling is treated as a **prerequisite**; replace the example commands with the paths or package names defined by your internal repository.

---

## Executive summary

You will (1) apply the official CRDs and controller manifests for cert-manager 1.17.1, (2) mint a private root CA with a `SelfSigned` `ClusterIssuer`, (3) delegate signing to a `CA` `ClusterIssuer`, (4) request a leaf certificate for an application namespace, and (5) optionally import the root into the macOS System Keychain so browsers trust your dev certificates.  The sequence follows cert-manager’s upstream documentation and proven patterns. ([cert-manager][1], [cert-manager][2], [cert-manager][3], [cert-manager][4])

---

## 1  Prerequisites

| Item                                                      | Tested version                             | Notes                                                                                      |
| --------------------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------ |
| **Existing single-node or multi-node Kubernetes cluster** | 1.24 – 1.33 (cert-manager supported range) | Cluster must be reachable by `kubectl`. ([cert-manager][5])                                |
| **`kubectl` CLI**                                         | 1.33.0                                     | Ship via internal repo; needed for all apply/inspect steps.                                |
| **cert-manager release YAMLs**                            | 1.17.1                                     | Retrieve once from GitHub and store on an internal artefact server. ([GitHub][6])          |
| **macOS administrator account** (optional)                | —                                          | Required only to insert the root CA into `/Library/Keychains/System.keychain`. ([SS64][7]) |
| **CA-trust script tools**: `base64`, `security`           | stock macOS                                | `security add-trusted-cert` manipulates the Keychain. ([SS64][7])                          |

> **No public package managers**
> In tightly-controlled networks you cannot run `brew install` or pull manifests directly from the Internet.  Mirror the YAML files and binaries in an approved location, then substitute the URLs/paths in the commands below. ([Kubernetes][8])

---

## 2  Deploy cert-manager

### 2.1 Install CRDs and controller components

```bash
# Replace URL with your internal mirror
kubectl apply -f cert-manager.crds.yaml     # CRDs
kubectl apply -f cert-manager.yaml          # controller, webhook, cainjector
```

The CRDs must be applied **before** the controller, per upstream docs. ([cert-manager][1])

### 2.2 Wait for all Pods to be Running

```bash
kubectl get pods -n cert-manager
```

All three Deployments (`cert-manager`, `cert-manager-webhook`, `cert-manager-cainjector`) should report **Running / 1-1 READY** within 30–60 s.  Troubleshoot with the official guide if they remain `Pending` or `CrashLoopBackOff`. ([cert-manager][9])

---

## 3  Mint an internal root CA

### 3.1 Create a `SelfSigned` ClusterIssuer and root Certificate

```yaml
# 03-issuer-root.yaml
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
  commonName: my-root
  secretName: my-root-ca-secret
  duration: 87600h   # 10 years
  issuerRef:
    name: selfsigned-root
    kind: ClusterIssuer
```

```bash
kubectl apply -f 03-issuer-root.yaml
```

The `SelfSigned` issuer pattern is recommended by cert-manager for bootstrapping an internal PKI. ([cert-manager][2])

### 3.2 Verify root objects

```bash
kubectl get clusterissuer selfsigned-root
kubectl -n cert-manager get certificate my-root-ca
```

Both resources should show **READY =True**.

---

## 4  Create a CA Issuer for leaf certificates

```yaml
# 04-ca-issuer.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: my-ca-issuer
spec:
  ca:
    secretName: my-root-ca-secret
```

```bash
kubectl apply -f 04-ca-issuer.yaml
```

The `CA` issuer uses the private key stored in `my-root-ca-secret` to sign future certificates. ([cert-manager][3])

---

## 5  Request a test certificate (namespace `istio-system`)

```yaml
# 05-httpbin-cert.yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: httpbin-cert
  namespace: istio-system
spec:
  secretName: httpbin-tls
  commonName: httpbin.example.local
  dnsNames:
  - httpbin.example.local
  issuerRef:
    name: my-ca-issuer
    kind: ClusterIssuer
```

```bash
kubectl apply -f 05-httpbin-cert.yaml
kubectl -n istio-system get certificate httpbin-cert
```

A `READY=True` status confirms issuance; the key-pair and signed chain are stored in `httpbin-tls`. ([cert-manager][4])

---

## 6  (Optional) Trust the root CA on macOS

1. **Extract the root certificate**

   ```bash
   kubectl -n cert-manager get secret my-root-ca-secret \
     -o jsonpath='{.data.ca\.crt}' | base64 -d > my-root.crt
   ```

   The `jsonpath` query pulls the `ca.crt` field from the secret and decodes it from Base64. ([Kubernetes][8])

2. **Add it to the System Keychain**

   ```bash
   sudo security add-trusted-cert -d -r trustRoot \
        -k /Library/Keychains/System.keychain my-root.crt
   ```

   `security add-trusted-cert` inserts the certificate as a root-trusted anchor; `-d` targets the system-wide store. ([SS64][7])

After this step, browsers and CLI tools on your Mac will trust any certificate signed by `my-ca-issuer`.

---

## 7  Validation checklist

| Check                         | Command                                                                                             | Expected output          |
| ----------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------ |
| All cert-manager pods Running | `kubectl get pods -n cert-manager`                                                                  | `Running 1/1`            |
| Root CA secret present        | `kubectl -n cert-manager get secret my-root-ca-secret`                                              | `TYPE kubernetes.io/tls` |
| CA Issuer ready               | `kubectl get clusterissuer my-ca-issuer -o jsonpath='{.status.conditions[0].status}'`               | `True`                   |
| Leaf Cert ready               | `kubectl -n istio-system get certificate httpbin-cert -o jsonpath='{.status.conditions[0].status}'` | `True`                   |
| TLS secret populated          | `kubectl -n istio-system get secret httpbin-tls`                                                    | `DATA 3`                 |

If any row fails, see the official troubleshooting guide. ([cert-manager][9])

---

## 8  Clean-up (optional)

```bash
kubectl delete -f 05-httpbin-cert.yaml
kubectl delete -f 04-ca-issuer.yaml
kubectl delete -f 03-issuer-root.yaml
kubectl delete -f cert-manager.yaml
kubectl delete -f cert-manager.crds.yaml
sudo security remove-trusted-cert my-root.crt   # removes trust from macOS
```

---

### Why this approach?

* **Self-contained PKI** – keeps dev certificates off public ACME CAs.
* **CRD-first installation** – aligns with cert-manager’s recommended order, avoiding race conditions. ([cert-manager][1])
* **Root-then-CA model** – clean separation between one-time root generation and day-to-day signing workflow. ([cert-manager][2], [cert-manager][3])
* **Optional host trust** – needed only when you test via a browser or client that validates TLS.  The macOS `security` CLI lets you automate trust without UI clicks. ([SS64][7])

You now have a reproducible process for bootstrapping cert-manager 1.17.1 in any on-prem or air-gapped cluster—no external package manager required.

[1]: https://cert-manager.io/docs/installation/kubectl/?utm_source=chatgpt.com "kubectl apply - cert-manager Documentation"
[2]: https://cert-manager.io/docs/configuration/selfsigned/?utm_source=chatgpt.com "SelfSigned - cert-manager Documentation"
[3]: https://cert-manager.io/docs/configuration/ca/?utm_source=chatgpt.com "CA - cert-manager Documentation"
[4]: https://cert-manager.io/docs/usage/certificate/?utm_source=chatgpt.com "Certificate resource - cert-manager Documentation"
[5]: https://cert-manager.io/docs/releases/?utm_source=chatgpt.com "Supported Releases - cert-manager Documentation"
[6]: https://github.com/cert-manager/cert-manager/releases?utm_source=chatgpt.com "Releases · cert-manager/cert-manager - GitHub"
[7]: https://ss64.com/mac/security-cert.html?utm_source=chatgpt.com "security - cert - macOS - SS64.com"
[8]: https://kubernetes.io/docs/tasks/configmap-secret/managing-secret-using-kubectl/?utm_source=chatgpt.com "Managing Secrets using kubectl - Kubernetes"
[9]: https://cert-manager.io/docs/troubleshooting/?utm_source=chatgpt.com "Troubleshooting - cert-manager Documentation"
