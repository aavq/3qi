## 1. System Overview

*Capture basic System identity and ownership.*

* **System Name**: `{{Enter}}`
* **Template Version**: 1.0.0 (12 June 2025)
* **Design Review Date**: `{{Enter}}`
* **Work Groups / Contributors**: `{{Name, team, contact}}`
* **Teams Channel**: `{{Link}}`

## 2. Key Stakeholders

*HC Core, Business, SRE, SEC, Network, DC Ops, etc.*

| Name & Role | Team | Contact |
| ----------- | ---- | ------- |

## 3. Feasibility Assessment

*Summarise PoC results, TCO, rack space, power, cooling.*

* Status: Completed | In Progress | Not Required
* Key Findings (link to report)
* Reference SDD feasibility formats

## 4. Scope & Business Reason

*Charter, boundaries, KPIs, target customers.*

## 5. Design Approach

*Logical -> high-level physical; include diagrams.*

* Methodology (12-factor, Googole, AWS, Asure, etc.)
* Logical diagram (services, flows)
* Physical diagram (nodes, racks, networks)
* Supporting artefacts: Helm-chart dependency graphs, CI/CD pipeline sketches
* Align with CNCF cluster architecture concepts

## 6. Constraints and Limitations

*Technical (e.g. Kubernetes v1.29), budget (Euro ...), schedule (Q4 2025).*

## 7. Dependencies

*Other apps, services, organisational changes, release gates.*

## 8. Assumptions

*Explicit for smoother reviews.*

## 9. Risks & Mitigations

*List, probability, impact, mitigation plan.*

## 10. Design Alternatives

*Option A/B/C with selection criteria and rationale.*

## 11. Reporting & Processes

*Logging, metrics, dashboards, SLO/SLI targets (p95 latency, error budget). Sources for SLO patterns*

## 12. System Interfaces

*Ingress/egress, APIs, third-party integrations (LDAP, CMDB, GitOps repos, etc.).*

## 13. User Interfaces

*CLI (kubectl plugins), Web UI (ArgoCD, Backstage portal, Kubernetes Dashboard).*

## 14. Fault Management

*Failure modes, alerting, auto-healing, runbooks; include etcd snapshot/restore procedures per Kubernetes DR docs*

## 15. Existing Defects Resolved

*Link Jira issues closed by this design.*

## 16. Compliance

*GDPR, ISO 27001, BCP, industry-specific regs.*

## 17. Architectural Scalability

*Horizontal/vertical growth (node pools, multi-rack/AZ).*

## 18. Usability & Accessibility

*Persona-based ease of use, accessibility guidelines.*

## 19. Security

*Data types (PII, logs, secrets); authentication (OIDC, x-509); RBAC/namespace isolation; reference ARMO on-prem security guidance*

## 20. Performance & Reliability

*Target SLA/SLO, capacity headroom.*

## 21. Network & Remote Access

*CNI choice (e.g., Calico), patterns.*

## 22. Data & Files

*Storage classes (Ceph RBD/NFS), schema flows, backup strategy.*

## 23. Testing

*Unit, integration, chaos, performance; last report date.*

## 24. Hardware & Operating System

*Server models, CPU/RAM, OS (e.g., RHEL 9).*

## 25. Deployment

*Cluster API, Ansible, Metal LB; GitOps pipeline stages.*

## 26. Cost

*CAPEX vs. OPEX breakdown; maintenance resources.*

## 27. Disaster Recovery

*RPO/RTO, quarterly DR drills, etcd snapshot frequency.*

## 28. Operations

*Patch management, inventory, audit, report distribution.*

## 29. Special Design Issues

*Licensing, GPU nodes, air-gapped constraints, anything not covered above.*

---

### How to Use This Template

1. Copy the file into the project repository.
2. Fill all *italicised mandatory* fields in the first pass.
3. Attach diagrams and CI/CD artefacts for each design review iteration.

This template unifies proven SDD conventions([cms.gov][1], [voa.va.gov][5], [ntrs.nasa.gov][2]) with current on-prem Kubernetes guidance([armosec.io][3], [groundcover.com][4], [kubernetes.io][6]) and disaster-recovery practices for etcd([kubernetes.io][8], [spectrocloud.com][9], [docs.oracle.com][10]), ensuring complete coverage from business goals to operations and DR.

[1]: https://www.cms.gov/Research-Statistics-Data-and-Systems/CMS-Information-Technology/TLC/Downloads/System-Design-Document.docx?utm_source=chatgpt.com "[DOC] System-Design-Document.docx - CMS"
[2]: https://ntrs.nasa.gov/api/citations/20160011412/downloads/20160011412.pdf?utm_source=chatgpt.com "[PDF] System Design Document (SDD)"
[3]: https://www.armosec.io/blog/kubernetes-on-premises/?utm_source=chatgpt.com "Kubernetes On-Premises Best Practices & Guidelines - ARMO"
[4]: https://www.groundcover.com/blog/kubernetes-on-premises?utm_source=chatgpt.com "Kubernetes On-Premises: Benefits, Challenges & Best Practices"
[5]: https://www.voa.va.gov/DocumentView.aspx?DocumentID=197&utm_source=chatgpt.com "[DOC] System Design Document Template - VA VOA Home"
[6]: https://kubernetes.io/docs/concepts/architecture/?utm_source=chatgpt.com "Cluster Architecture | Kubernetes"
[7]: https://www.apptio.com/topics/kubernetes/best-practices/?utm_source=chatgpt.com "Best Practices - Kubernetes Guides - Apptio"
[8]: https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/?utm_source=chatgpt.com "Operating etcd clusters for Kubernetes"
[9]: https://www.spectrocloud.com/blog/kubernetes-backup-and-restore-done-right?utm_source=chatgpt.com "Kubernetes backup and restore done right - Spectro Cloud"
[10]: https://docs.oracle.com/en/solutions/kubernetes-restore-etcd-snapshot/configure-disaster-recovery.html?utm_source=chatgpt.com "Kubernetes clusters restore based on etcd snapshots"
