import json
import pathlib
import re


def test_issue244_freeform():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    wizard_js_path = repo_root / "app" / "js" / "wizard.js"
    openapi_json_path = repo_root / "backend" / "openapi.json"

    text = wizard_js_path.read_text(encoding="utf-8")

    # Structural contract: const Wizard declaration
    assert "const Wizard" in text

    # All required methods must be present, followed by ( or :
    methods = [
        "init",
        "refresh",
        "loadDefinitions",
        "createDefinition",
        "selectDefinition",
        "loadSteps",
        "createStep",
        "deleteStep",
        "loadFlows",
        "createFlow",
        "deleteFlow",
        "generate",
        "downloadXml",
        "downloadSvg",
        "_esc",
        "_notice",
        "_toast",
    ]
    for m in methods:
        assert re.search(
            rf"\b{m}\s*[\(:]", text
        ), f"Method {m} not found followed by ( or :"

    # Data access must NEVER use raw fetch()
    assert "fetch(" not in text

    # Module exports guard must be present
    assert "module.exports = { Wizard }" in text

    # API paths relative to /api base must occur in the module
    for p in ["/process-definitions", "/process-steps", "/sequence-flows", "/generate"]:
        assert p in text, f"Path {p} missing from wizard.js"

    # Verify targets exist on the real backend OpenAPI contract
    openapi = json.loads(openapi_json_path.read_text(encoding="utf-8"))
    paths = openapi.get("paths", {})
    for api_p in [
        "/api/process-definitions",
        "/api/process-steps",
        "/api/sequence-flows",
        "/api/process-definitions/{definition_id}/generate",
    ]:
        assert api_p in paths, f"OpenAPI path {api_p} missing from backend contract"

    # Step type select must contain exactly these five option literals
    for opt in [
        '<option value="start">',
        '<option value="end">',
        '<option value="user">',
        '<option value="service">',
        '<option value="gateway">',
    ]:
        assert opt in text, f"Option literal {opt} missing from wizard.js"

    # All required DOM ids must be referenced in the module
    dom_ids = [
        "wizard-definitions",
        "wizard-def-name",
        "wizard-steps",
        "wizard-step-type",
        "wizard-flows",
        "wizard-flow-source",
        "wizard-flow-target",
        "wizard-generate",
        "wizard-svg",
        "wizard-download-xml",
        "wizard-download-svg",
    ]
    for did in dom_ids:
        assert did in text, f"DOM id {did} missing from wizard.js"

    # Envelope contract: must read .data, never index the envelope itself
    assert ".data" in text

    # Payload field literals must match backend schema exactly
    for field in [
        "source_step",
        "target_step",
        "condition_expression",
        "candidate_groups",
    ]:
        assert field in text, f"Payload field {field} missing from wizard.js"

    # IDs are opaque strings; parseInt is strictly forbidden
    assert "parseInt" not in text
