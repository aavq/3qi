---
title: "{{ system_name }}-Design Doc"
version: 1.0.0                # major = structural, minor = section added, patch = editorial
last_reviewed: 2025-07-18
owner: "{{ team_name }}"
status: Draft | In Review | Approved
tags: [sdd, {{platform}}, {{domain}}]
---

<!-- `markdown-toc` GitHub Action injects a TOC here on push -->
<!-- toc -->

# Executive-Summary
* **Business Goal** - _e.g. cut onboarding time by-50-%_
* **Key Success Metric(s)** - latency-p95-=<-150-ms
* **Top 3 Risks & Mitigations** - single-region storage -> multi-AZ, etc.
* **System-Context Diagram** - `diagrams/system-context.puml`

# 1-Context-&-Scope
Describe the problem solved, measurable value, and boundaries (what is **out** of scope). Include main stakeholders and links to slack/Teams channels.

# 2-Architecture Overview (C4-L1-L2)
* Structurizr DSL files live in `diagrams/` and render via CI to PNG
* System-Context + Container diagrams only; L3-L4 kept on demand
* Key technology choices (k8s, Istio, Postgres) with one-line rationale

# 3-Non-Functional Requirements (Table)
| Category      | Metric              | Target |
|---------------|---------------------|--------|
| **Availability** | SLO 99.9-%        | =<-43-min-downtime /-month |
| **Performance**  | p95 latency       | =<-150-ms |
| **Security**     | GDPR compliance   | **Yes** |
| **Observability**| trace-sample rate | >=-95-% flows |

# 4-Reliability (Ops-+-DR combined)
* **SLIs/SLOs & Error-Budget Policy**
* **Alert -> Runbook -> Escalation** chain (links)
* **Disaster-Recovery** - etcd snapshot every 8-h; quarterly restore drill (`runbooks/etcd-restore.md`)
* **Autoscaling & Capacity** - HPA targets, resource budgets

# 5-Architectural Decisions (ADR Index)
ADR logs live in `docs/adr/`. List latest IDs and titles for quick lookup.

# 6-Change-Log
| Version | Date | Author | Summary |
|---------|------|--------|---------|
| 1.0.0   | 2025-07-18 | {{your_name}} | Initial lean template |

---

## Appendix-A - Production-Readiness Checklist  <!-- optional -->
- [ ] Load test >=-2 peak traffic  
- [ ] Verified rollback (blue/green)  
- [ ] PagerDuty on-call rota created  
- [ ] >-90-% coverage of SLO alerts  
*(Full list: `checklists/prr.md`)*

## Appendix-B - Security & SBOM Checklist  <!-- optional -->
- [ ] SBOM (CycloneDX) produced in CI
- [ ] SLSA level-3 provenance stored
- [ ] STRIDE threat model completed  
*(Template: `checklists/security.md`)*

## Appendix-C - Glossary / References  <!-- optional -->
Link to terms, external standards, etc.
