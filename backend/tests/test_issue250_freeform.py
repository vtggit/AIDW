"""Proving test for Issue #250 — freeform wizard acceptance criteria.

Validates that app/index.html preserves every existing element and adds the
Process wizard section, and that app/tests/250_ac_1.spec.js contains the
required Playwright assertions.
"""

from pathlib import Path


def test_issue250_freeform():
    repo_root = Path(__file__).resolve().parents[2]
    index_path = repo_root / "app" / "index.html"
    spec_path = repo_root / "app" / "tests" / "250_ac_1.spec.js"

    html = index_path.read_text(encoding="utf-8")
    spec = spec_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Must-retain stylesheet hrefs (six)
    # ------------------------------------------------------------------
    # bpmn-js retired (VTG-ADOPT-001 follow-through): the canvas, its vendored assets,
    # and workflows.css are gone; the wizard is the only authoring surface.
    for href in [
        "css/styles.css",
        "css/warehouse.css",
    ]:
        assert href in html, f"Missing stylesheet href: {href}"

    # ------------------------------------------------------------------
    # Must-retain header id auth-status
    # ------------------------------------------------------------------
    assert 'id="auth-status"' in html

    # ------------------------------------------------------------------
    # Must-retain section ids and controls
    # ------------------------------------------------------------------
    for ctrl_id in [
        "source-form",
        "src-name",
        "src-endpoint",
        "src-version",
        "src-submit",
        "sources",
        "inbox-count",
        "inbox",
        "dashboards",
        "pii-count",
        "pii-inbox",
    ]:
        assert f'id="{ctrl_id}"' in html, f"Missing control id: {ctrl_id}"

    # ------------------------------------------------------------------
    # Must-retain div id toast
    # ------------------------------------------------------------------
    assert 'id="toast"' in html

    # ------------------------------------------------------------------
    # Eight script srcs in strict order (seven existing + js/wizard.js)
    # ------------------------------------------------------------------
    scripts = [
        "js/config.js",
        "js/auth.js",
        "js/api.js",
        "js/warehouse.js",
        "js/sources.js",
        "js/wizard.js",
    ]

    prev_pos = -1
    for src in scripts:
        pos = html.find(src)
        assert (
            pos > prev_pos
        ), f"Script {src} not found or out of order (pos={pos}, prev={prev_pos})"
        prev_pos = pos

    # ------------------------------------------------------------------
    # Wizard.init() inside DOMContentLoaded inline script
    # ------------------------------------------------------------------
    dc_start = html.find("DOMContentLoaded")
    assert dc_start >= 0, "DOMContentLoaded handler not found"
    dc_block = html[dc_start:]
    assert (
        "Wizard.init();" in dc_block
    ), "Wizard.init(); missing from DOMContentLoaded handler"

    # ------------------------------------------------------------------
    # Five step-type option literals
    # ------------------------------------------------------------------
    for opt in [
        '<option value="start">',
        '<option value="end">',
        '<option value="user">',
        '<option value="service">',
        '<option value="gateway">',
    ]:
        assert opt in html, f"Missing step-type option: {opt}"

    # ------------------------------------------------------------------
    # Every wizard-* id listed above occurs
    # ------------------------------------------------------------------
    wizard_ids = [
        "wizard-notice",
        "wizard-toast",
        "wizard-def-name",
        "wizard-def-key",
        "wizard-create-def-btn",
        "wizard-definitions",
        "wizard-step-name",
        "wizard-step-key",
        "wizard-step-ordinal",
        "wizard-step-type",
        "wizard-step-service-impl",
        "wizard-step-groups",
        "wizard-step-form-key",
        "wizard-create-step-btn",
        "wizard-steps",
        "wizard-flow-name",
        "wizard-flow-key",
        "wizard-flow-source",
        "wizard-flow-target",
        "wizard-flow-condition",
        "wizard-flow-default",
        "wizard-create-flow-btn",
        "wizard-flows",
        "wizard-generate",
        "wizard-download-xml",
        "wizard-download-svg",
        "wizard-svg",
    ]
    for wid in wizard_ids:
        assert f'id="{wid}"' in html, f"Missing wizard id: {wid}"

    # ------------------------------------------------------------------
    # vendor/bpmn-js occurs at least five times (stylesheets + modeler script)
    # ------------------------------------------------------------------
    # bpmn-js retired: no vendor reference may remain anywhere in the page.
    assert "vendor/bpmn-js" not in html, "retired vendor/bpmn-js still referenced"

    # ------------------------------------------------------------------
    # Spec file contains required tokens
    # ------------------------------------------------------------------
    for token in [
        "test(",
        "data-testid",
        "wizard-definitions",
        "wizard-generate",
        "wizard-svg",
        "BASE_URL",
    ]:
        assert token in spec, f"Missing token in spec: {token}"
