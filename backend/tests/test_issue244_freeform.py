import json
import re
from pathlib import Path


def test_issue244_freeform():
    repo_root = Path(__file__).resolve().parents[2]

    js_path = repo_root / "app" / "js" / "wizard.js"
    assert js_path.exists(), f"{js_path} not found"
    js_text = js_path.read_text()

    openapi_path = repo_root / "backend" / "openapi.json"
    assert openapi_path.exists(), f"{openapi_path} not found"
    with open(openapi_path) as f:
        openapi_data = json.load(f)

    # 1. const Wizard
    assert "const Wizard" in js_text

    # 2. method names followed by ( or :
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
        assert re.search(rf"{m}\s*[\(:]", js_text), f"Method {m} not found with ( or :"

    # 3. NEVER contains fetch(
    assert "fetch(" not in js_text

    # 4. module.exports guard exporting Wizard is present
    assert re.search(r"module\.exports\s*=\s*\{\s*Wizard\s*\}", js_text)

    # 5. path strings occur in the text
    for p in ["/process-definitions", "/process-steps", "/sequence-flows", "/generate"]:
        assert p in js_text, f"Path {p} not found in JS"

    # 6. openapi.json paths exist on the real backend contract
    api_paths = openapi_data.get("paths", {})
    for p in [
        "/api/process-definitions",
        "/api/process-steps",
        "/api/sequence-flows",
        "/api/process-definitions/{definition_id}/generate",
    ]:
        assert p in api_paths, f"OpenAPI path {p} not found"

    # 7. each of the five literals occurs in the text
    options = [
        '<option value="start">',
        '<option value="end">',
        '<option value="user">',
        '<option value="service">',
        '<option value="gateway">',
    ]
    for opt in options:
        assert opt in js_text, f"Option {opt} not found in JS"

    # 8. each DOM id string occurs in the text
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
        assert did in js_text, f"DOM id {did} not found in JS"
