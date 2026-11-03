# AIDW Compliance Control Corpus (compliance-gate track)

The versioned control set the CodeAgent deliberation panel reasons against when an
issue touches regulated data or proposes a third-party adoption. This corpus follows
the **controls-not-law** principle:

1. **The law/regulation** (NIST SP 800-171, DFARS, GDPR, …) is *provenance* — a
   citation. Agents never interpret statute directly.
2. **The company control** is the human-ratified operative rule, traceable to that
   citation. This is what agents apply, and what a veto or condition must cite by id.
3. **The machine-checkable form** is the control plus applicability tags (`cui`,
   `adoption`, …), a severity, and a version.

## How the corpus is used

An issue that touches controlled data (or carries the `ca-adopt` label) references the
applicable control files **by path in its body**. Panel agents work from a checkout of this
repository, which is how they read those files; the engine does not paste them into the
prompt. Findings, vetoes, and ratification conditions must cite the control `id`. Every gate decision is judged against the corpus version in
force at that time; controls are amended by a deliberated issue + human ratification,
never edited silently.

## Registry

| id | family | source | CMMC | tags | severity |
|---|---|---|---|---|---|
| `800-171-3.1.1` | Access Control | NIST SP 800-171r2 §3.1.1 | L2 | cui | high |
| `800-171-3.1.3` | Access Control | NIST SP 800-171r2 §3.1.3 | L2 | cui | high |
| `800-171-3.3.1` | Audit & Accountability | NIST SP 800-171r2 §3.3.1 | L2 | cui | high |
| `800-171-3.8.3` | Media Protection | NIST SP 800-171r2 §3.8.3 | L2 | cui | high |
| `800-171-3.13.11` | System & Comms Protection | NIST SP 800-171r2 §3.13.11 | L2 | cui | high |
| `VTG-ADOPT-001` | Adoption Policy | company-authored | — | adoption | high |

**Ratification state:** all v1 controls ratified by the operator (interim ratifier —
theoretical-company phase, 2026-07-16). A future compliance authority re-ratifies on
assumption of the role.

**Proposed, not ratified:** `VTG-DEPLOY-001`, the trust-surface control for deploying an
executable BPMN definition to the workflow engine ([#290](https://github.com/vtggit/AIDW/issues/290),
draft [PR #292](https://github.com/vtggit/AIDW/pull/292)). It is not part of the corpus until
it is ratified.
