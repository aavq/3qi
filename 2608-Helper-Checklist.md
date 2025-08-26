# Helper. Checklist

---

## Document Lifecycle

- Why this document exists and who is supposed to use it.
- How to make changes: via Pull Requests to the `docs/` folder, with required reviewers from the list.
- How often the document must be reviewed/validated: every 'N' months. The responsible owner is a specific person/role.
- Criteria for the document's status:
  - **Draft** - content is being developed.
  - **In-Review** - the document is under review.
  - **Approved** - design/document is signed off.
  - **Active** - implemented and running in production; document is current.
  - **Deprecated** - decommission is planned; there is a sunset plan.
- A bulleted list of key changes with dates.*

---

## Purpose

- A short paragraph: what the component does and the value it delivers.
- Main audiences: tenants, platform team, SRE, security, billing, etc.
- Business goals, success metrics (SLI/SLO), and acceptance criteria.
- What is intentionally excluded from the scope.

---

## Design

- Describe the control-plane vs data-plane, which CRDs/operators/sidecars are involved, and how they connect. Document: namespaces, services, control-plane components, data flows, where sidecars sit (proxy, log agent), which operators manage CRDs.
- Dependencies.
  - In-cluster: list critical in-cluster extensions/services. CRDs, admission webhooks, CNI/CSI, cert-manager, Argo CD.
  - Out-of-cluster: external dependencies. DNS, PKI/CA, Vault/secrets backend, LDAP/OIDC for auth, storage (NetApp/Ceph), time sync (PTP/NTP).
- Describe inbound/outbound traffic (ingress/egress), ports/protocols, mTLS requirements, any multicast, and use of eBPF. Useful table: Source -> Destination -> Port/Protocol -> Direction -> Encryption (mTLS/TLS) -> Authentication -> NetworkPolicy rule.
- How the component survives failures: number of Pods per AZ/DC, PodDisruptionBudget, whether leader election is used. Practices: `topologySpreadConstraints`, `podAntiAffinity`, `PDB minAvailable: 1`, leader election via `coordination.k8s.io/Lease`.
- Requests/limits, CPU/memory service classes, NUMA/hugepages needs. Specify CPU Manager policy (`static` for whole-core pinning), Topology Manager (NUMA alignment), Guaranteed/Burstable QoS, required hugepages.
- Baselines: least privilege, `runAsNonRoot`, `readOnlyRootFilesystem`, limit Linux capabilities, trusted image registries, image signing/vuln scanning.
- Authentication/authorization: RBAC, service accounts, OIDC scopes. Example: roles limited to required API groups; SA with narrow rights; OIDC claims mapped to RBAC groups.
- Where/how secrets are stored/rotated: ESO paths (`ExternalSecrets` -> SM), rotation policy, KMS provider for encrypting Secrets in etcd.
- Baseline default-deny ingress/egress; allowed egresses (DNS, IdP, secrets store, metrics); namespace scoping; selectors.
- Data classes (PII/internal/public). Encryption in-transit (mTLS/TLS, versions/ciphers) and at-rest (disk/LUKS/KMS, K8s `EncryptionConfiguration`).
- Top 3 risks + mitigations
  - Service account token leakage. Mitigations: short TTL, audience binding, tight RBAC.
  - Supply-chain (malware in image). Mitigations: artifact signing, policy enforcement (Kyverno/Gatekeeper).
  - MITM on egress. Mitigations: mTLS/cert pinning.
- Typical behavior. traffic/throughput profile, peak loads, cold-start needs, DNS dependency/idempotency, logging/tracing/metrics requirements.
- Which indicators you measure: availability, latency (p95/p99), error rate, freshness (data age), sync lag (replication delay), queue depth.
- Targets for SLIs and the error budget (e.g., 99.9%/month). Describe how you "spend" the budget (feature flags, canaries) and violation procedure (freeze, RCA).
- Version compatibility (K8s/CRD/API), schema migrations, webhooks for CRD conversions, backward compatibility, rollback plan.
- How often to release, maintenance windows, how you announce breaking changes, deprecation window.
- Strategies: Blue/Green, canary, rolling update with surge; rollback plan (how and to which version). Note interactions with HPA/autoscaling and resource limits.
- What to back up and how to validate restores: state, CRDs (definitions and instances), config (ConfigMap/Secret), DB/object storage snapshots, etcd (if you manage the cluster).

---

## Deploy

- How we deliver a release: Helm charts, Kustomize overlays, GitOps via Argo CD. Provide links to repos/folders/Argo applications.
- List the environments: dev (development), uat (user acceptance testing), prd (production). Briefly describe how they differ (replicas, feature flags, limits, domains).
- For each environment/region, provide the path to the chart/overlay/Argo app and the parameters that must be overridden: external endpoints, quotas, RBAC permissions. Example: `values-prod.yaml` overrides `ingress.host`, `replicas`, `resourceQuota`.
- Where `values.yaml` (Helm) and Kustomize `overlays` live, how inheritance works, and the order of application.
- Pre-deployment checks: required cluster features, installed CRDs, available quotas, reachability of admission webhooks, working DNS, valid certificates, etc.
- Where the container image is stored and how it's signed (cosign if applicable). Provide the exact image reference and tags, plus retention policy(Optional).
- Where configs/secrets come from: plain `ConfigMap`/`Secret`, or External Secrets backed by GCP Secret Manager (or another vault). Include key formats, resource names, and namespaces.
- Networking resources that are created: `Namespace`, `Service`(ClusterIP/Headless), and exposure-either classic `Ingress` or Istio (`Gateway` + `VirtualService`). List domains/hosts/ports.
- If using Istio/ASM: mTLS mode (PERMISSIVE/STRICT), access policies (AuthorizationPolicy), traffic policies (DestinationRule, PeerAuthentication, etc.).
- How scaling works: HPA (CPU/Memory/Prometheus) or KEDA (external triggers such as Kafka, Pub/Sub, SQS, etc.). Include setpoints and min/max replicas. HPA example:* `cpu 70%`, min=2, max=10.
- Update/rollback procedures: commands (`argocd app rollback`), step order, and a compatibility matrix for versions (client/server, CRDs, operators).
- Resource and placement policies: `requests/limits`, nodeSelector/affinity/anti-affinity, tolerations, `securityContext` (UID/GID, capabilities), Pod Security requirements (baseline/restricted).
- Storage details: which `PVC`s, `StorageClass`es, sizes, backup/snapshot policy and retention. Identify what is stateful and how data migrations are handled.
- Bare-metal specifics: pinning to node types (CPU flags, NUMA, SR-IOV), "thick" StorageClasses, need for local disks, network topology.
- A full step-by-step plan beyond "click Sync": initial bootstrap, DB/schema migrations, one-off `Job`s/`initContainers`, traffic cutover.
- How to validate the deployment: smoke tests/scripts, readiness criteria (what exactly must respond), synthetic monitors/probes.
- Backout plan: exact commands/buttons, which git commit to revert to, and data impact (whether migrations need a downgrade or snapshot restore).

---

## Operate

- Links to dashboards (usually Grafana) and a short note on how to interpret the graphs: which panels are key, which thresholds are normal, and which indicate incidents.
- General list of alerts for the component.
- Rules (name, expr, severity, page or ticket). Table of alert rules:
  - `name` - rule name;
  - `expr` - expression (PromQL) for triggering;
  - `severity` - criticality (critical/warning/info);
  - `page or ticket` - action: page on-call (PagerDuty, Opsgenie, etc.) or create ticket (Jira).
- Links per alert for each alert - link to a runbook: step-by-step instructions (checks, commands, criteria for "fixed").
- Common Ops: scale, rotate certs/keys, drain nodes, webhooks stuck, CRD skew. Common operational tasks with short procedures:
  - scale - how to scale Deployment/StatefulSet (via HPA, manually with `kubectl scale`, limits);
  - rotate certs/keys - rotation of TLS certs/keys (source, expiry, who must restart);
  - drain nodes - safe node eviction (`kubectl drain`, tolerations, PodDisruptionBudget);
  - webhooks stuck - what to do if admission/mutating webhook hangs and blocks Pod creation;
  - CRD skew - version drift of CRDs across clusters/controllers and consequences (validation, stored versions).
- Incident triage: symptoms -> checks -> actions -> verify -> comms -> postmortem. Standard incident funnel:
  1. symptoms - what the problem looks like (user impact, metrics);
  2. checks - quick checks (SLO, logs, `kubectl get`, dependencies health);
  3. actions - allowed mitigations/rollbacks/feature toggles;
  4. verify - how to confirm the fix;
  5. comms - who and how to notify (status channel, incident room, update template);
  6. postmortem - structured incident review (timeline, root cause, RCA actions).
- Maintenance (upgrade SOPs, cert rotations, webhook timeouts, GC & compaction). Regular maintenance:
 - upgrade SOPs - standard operating procedures for upgrades (versions, order, rollback plan, maintenance window);
 - cert rotations - planned certificate rotations;
 - webhook timeouts - timeout settings to avoid API blocking;
 - GC & compaction - garbage collection/compaction (for etcd, image registry, log storage).
- Capacity and Cost (cardinality, etcd objects, images count, storage footprint). Capacity and cost management:
  - images count - number of images/tags in registry (cleanup, retention);
  - etcd objects - how many objects are stored in etcd (limits, growth);
  - cardinality - monitoring metric cardinality (label explosion in Prometheus);
  - storage footprint - disk usage (PVs, images, backups).
- Security Ops (CVE handling, image signing/verif, policy updates). Operational security practices:
  - CVE handling - triaging and patching vulnerabilities, timelines;
  - image signing/verif - container image signing and verification (cosign/Notary, admission enforcement);
  - policy updates - keeping security policies updated (OPA/Gatekeeper/Kyverno, Pod Security, NetworkPolicy).
- DR/Backup (what's backed up, frequency, restore test cadence & RTO/RPO proof). Disaster recovery and backups:
  - what is backed up (etcd, manifests/Helm charts, secrets, PV snapshots, image registry);
  - frequency - backup schedule;
  - restore test cadence - how often we test restores;
  - RTO/RPO proof - evidence of meeting RTO/RPO targets (measurements, reports).

---

# Appendices
- Port matrix, Config parameters table, Known issues, FAQ, Glossary, ADR links
  - Port matrix - table of ports/protocols/directions and purpose;
  - Config parameters table - all tunable parameters with defaults and valid ranges;
  - Known issues - known limitations/bugs and workarounds;
  - FAQ - frequently asked questions with short answers;
  - Glossary - terminology;
  - ADR links - references to Architecture Decision Records (history of major design decisions).

---
