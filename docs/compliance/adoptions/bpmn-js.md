# Adoption record: bpmn-js (bpmn.io BPMN modeling toolkit)

- **Component:** `bpmn-js` 18.21.0 (+ bundled `diagram-js`, `bpmn-moddle`) — bpmn.io / Camunda Services GmbH
- **Use:** in-product BPMN 2.0 authoring in AIDW's own UI (vendored prebuilt browser bundle, no bundler), per the ratified Flowable adoption ADR ([AIDW#189](https://github.com/vtggit/AIDW/issues/189)) — **never** the Flowable/Camunda enterprise modeler.
- **Tier:** open-source. **Status:** adopted-with-conditions. **Ratified by:** operator (interim ratifier — theoretical-company phase), 2026-07-19.

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

- **Enforcement:** `app/css/workflows.css` deliberately adds no rule that touches `.bjs-powered-by`;
  the toolbar sits above the canvas so nothing overlaps the bottom-right logo.
- **Verified live:** `app/tests/workflows.spec.js` asserts `.bjs-powered-by` is visible with a
  non-zero bounding box on the deployed frontend (passed).

## Scope boundary (governed follow-up)

This adoption covers **authoring only** (author / open / export BPMN 2.0 XML — client-side, no
execution surface). **Deploying** an authored definition to the Flowable engine is a separate,
governed decision: an authored BPMN can embed script tasks, service-task classes, listeners, and
external URLs that execute in the engine — a materially larger trust surface than the
opaque-reference allowlist. That seam lands later through CodeAgent (a `deploy_definition` op +
deploy endpoint on the sidecar-proxy lane) gated on a trust-surface ratification (admin-only? body
size cap? BPMN schema validation / script-task policy?).
