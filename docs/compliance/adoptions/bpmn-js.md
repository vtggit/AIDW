# Adoption record: bpmn-js (bpmn.io BPMN modeling toolkit)

- **Component:** `bpmn-js` 18.21.0 (+ bundled `diagram-js`, `bpmn-moddle`) — bpmn.io / Camunda Services GmbH
- **Use:** in-product BPMN 2.0 authoring in AIDW's own UI (vendored prebuilt browser bundle, no bundler), per the ratified Flowable adoption ADR ([AIDW#189](https://github.com/vtggit/AIDW/issues/189)) — **never** the Flowable/Camunda enterprise modeler.
- **Tier:** open-source. **Status:** **DEPENDENCY REMOVED 2026-07-22** (was adopted-with-conditions, ratified by operator 2026-07-19). See the retirement record at the end of this file.

## Licence (VTG-ADOPT-001 — verified, not assumed)

`bpmn-js` ships a custom **bpmn.io licence = MIT + one mandatory watermark clause**:

> The source code responsible for displaying the bpmn.io project watermark that links back to
> https://bpmn.io … MUST NOT be removed or changed. When this software is being used in a website
> or application, the watermark must stay fully visible and not visually overlapped by other elements.

The sibling packages (`diagram-js`, `bpmn-moddle`, `bpmn-js-properties-panel`) are **plain MIT**.

**Key finding:** the watermark obligation is a pure *attribution* requirement — there is **no paid
tier that removes it**, so it can never become a hidden enterprise-edition hook. bpmn-js therefore
**passes VTG-ADOPT-001**: every core function works in the open-source tier with zero paid/EE
dependency.

## Ratified condition (encoded + verified)

**The bpmn.io watermark that bpmn-js renders (bottom-right of the canvas, hyperlinked to
https://bpmn.io) MUST remain fully visible and unaltered — do not remove, hide, resize,
reposition, restyle, or visually overlap it, and do not modify the source that displays it.**
Retain the vendored `LICENSE` + `Copyright (c) 2014-present Camunda Services GmbH` notice (and the
MIT notices for the siblings) in shipped bundles.

- **Enforcement:** `app/css/workflows.css` carries an **explicit protective rule** —
  `.bpmn-canvas .bjs-powered-by svg { height: auto !important; width: auto !important; }` — which
  restores the mark to its intrinsic `width="53" height="21"`. This is required because the canvas
  fill rule (`.bpmn-canvas svg { height/width: 100% !important }`) is a *descendant* selector and
  therefore also matches the watermark's own `<svg>`. The toolbar sits above the canvas so nothing
  overlaps the bottom-right logo.
  > **Correction (supersedes the earlier wording).** This record previously stated that the CSS
  > "deliberately adds no rule that touches `.bjs-powered-by`". That was **false as written**: the
  > fill rule matched the mark's `<svg>`. A measured review confirmed the mark nevertheless rendered
  > correctly — natural 53×21, fully visible, unobstructed at three hit-tested points, still linked
  > to bpmn.io — because the anchor is absolutely positioned and shrink-to-fit, so the percentages
  > resolved back to the intrinsic size. So this was **latent fragility plus a documentation defect,
  > not a live breach**: compliance rested on an accident of the vendored bundle's layout, and an
  > auditor grepping `.bjs-powered-by` got a false negative. The explicit rule above closes both.
- **Verified live:** `app/tests/workflows.spec.js` asserts `.bjs-powered-by` is visible, still
  hyperlinked to bpmn.io, and that the logo's **rendered box equals its intrinsic size** — not
  merely that the box is non-zero. (A stretched or clipped mark also has a non-zero box, so the
  previous assertion could not have caught the regression this rule guards against.)
  **Caveat:** the Playwright suite runs in `codeagent-merge-gate.yml` under proof-family detection,
  **not** in the six standard CI checks — so this assertion does not blanket-block an unrelated CSS
  change. Treat it as a regression guard for frontend-proof work, not a universal gate.

## Scope boundary (governed follow-up)

This adoption covers **authoring only** (author / open / export BPMN 2.0 XML — client-side, no
execution surface). **Deploying** an authored definition to the Flowable engine is a separate,
governed decision: an authored BPMN can embed script tasks, service-task classes, listeners, and
external URLs that execute in the engine — a materially larger trust surface than the
opaque-reference allowlist. That seam lands later through CodeAgent (a `deploy_definition` op +
deploy endpoint on the sidecar-proxy lane) gated on a trust-surface ratification (admin-only? body
size cap? BPMN schema validation / script-task policy?).

## Retirement record (2026-07-22)

**bpmn-js no longer ships.** Path B replaced canvas authoring with the Process wizard: rows in
`process_definitions` / `process_steps` / `sequence_flows` are the source of truth, and the
server-side generator (`backend/app/bpmn/`) emits the BPMN 2.0 XML + SVG deterministically. The
wizard UI (PR 249 + PR 253, both merged, real-browser proven) made the canvas redundant.

Removed in this change: `app/vendor/bpmn-js/` (the vendored bundle, its assets, and its LICENSE
copy), `app/js/workflows.js` (the canvas module), `app/css/workflows.css` (the canvas +
watermark-protection rules), `app/tests/workflows.spec.js` (the watermark regression spec), and
every reference in `app/index.html`.

**Obligation status: ENDED, honoured to the last shipped build.** The watermark clause binds only
while the software is used in the product; the mark stayed fully visible and unaltered in every
build that carried bpmn-js (enforced by the workflows.spec.js assertions and the protective CSS
documented above). With the dependency gone, no attribution obligation remains. The generator and
the wizard contain no bpmn.io / Camunda code: `diagram-js` and `bpmn-moddle` never shipped
separately, and the emitted XML/SVG are house string templates.

The **scope boundary** above (deploy-to-engine is a separate governed seam) is unaffected and
remains the standing rule for the wizard-authored definitions.
