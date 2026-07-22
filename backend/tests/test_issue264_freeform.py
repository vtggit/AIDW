from pathlib import Path


def test_issue264_freeform():
    repo_root = Path(__file__).resolve().parents[2]
    studio_path = repo_root / "app" / "studio.html"
    text = studio_path.read_text()

    # Two stylesheet hrefs
    assert 'href="css/styles.css"' in text
    assert 'href="css/warehouse.css"' in text

    # Auth status
    assert 'id="auth-status"' in text

    # Nav dashboard link
    assert 'href="index.html"' in text
    assert 'data-testid="nav-dashboard"' in text

    # Toast
    assert 'id="toast"' in text

    # Data sources controls
    assert 'id="sources-count"' in text
    assert 'id="source-form"' in text
    assert 'id="src-name"' in text
    assert 'id="src-endpoint"' in text
    assert 'id="src-version"' in text
    assert 'id="src-submit"' in text
    assert 'id="sources"' in text

    # Suggested dashboard items controls
    assert 'id="inbox-count"' in text
    assert 'id="inbox"' in text

    # PII flags controls
    assert 'id="pii-count"' in text
    assert 'id="pii-inbox"' in text

    # Wizard — definitions block
    assert 'id="wizard-def-name"' in text
    assert 'id="wizard-def-key"' in text
    assert 'id="wizard-create-def-btn"' in text
    assert 'id="wizard-definitions"' in text

    # Wizard — steps block
    assert 'id="wizard-step-name"' in text
    assert 'id="wizard-step-key"' in text
    assert 'id="wizard-step-ordinal"' in text
    assert 'id="wizard-step-type"' in text
    assert 'id="wizard-step-service-impl"' in text
    assert 'id="wizard-step-groups"' in text
    assert 'id="wizard-step-form-key"' in text
    assert 'id="wizard-create-step-btn"' in text
    assert 'id="wizard-steps"' in text

    # Wizard — flows block
    assert 'id="wizard-flow-name"' in text
    assert 'id="wizard-flow-key"' in text
    assert 'id="wizard-flow-source"' in text
    assert 'id="wizard-flow-target"' in text
    assert 'id="wizard-flow-condition"' in text
    assert 'id="wizard-flow-default"' in text
    assert 'id="wizard-create-flow-btn"' in text
    assert 'id="wizard-flows"' in text

    # Wizard — generate block
    assert 'id="wizard-generate"' in text
    assert 'id="wizard-download-xml"' in text
    assert 'id="wizard-download-svg"' in text
    assert 'id="wizard-svg"' in text

    # Step-type option literals (exactly five)
    assert '<option value="start">' in text
    assert '<option value="end">' in text
    assert '<option value="user">' in text
    assert '<option value="service">' in text
    assert '<option value="gateway">' in text

    # Source-version option literals (exactly two)
    assert '<option value="v4">' in text
    assert '<option value="v2">' in text

    # Six script srcs occur in strictly increasing string-find order
    scripts = [
        "js/config.js",
        "js/auth.js",
        "js/api.js",
        "js/warehouse.js",
        "js/sources.js",
        "js/wizard.js",
    ]
    positions = [text.find(s) for s in scripts]
    assert all(positions[i] < positions[i + 1] for i in range(len(positions) - 1))

    # Warehouse.init(), Sources.init() and Wizard.init(); occur after the last script tag position
    _script_opens = []
    _pos = 0
    while True:
        _idx = text.find("<script", _pos)
        if _idx == -1:
            break
        _script_opens.append(_idx)
        _pos = _idx + 1
    last_script_open = _script_opens[-1]

    assert text.find("Warehouse.init()") > last_script_open
    assert text.find("Sources.init()") > last_script_open
    assert text.find("Wizard.init();") > last_script_open

    # Must NOT reference js/charts.js
    assert "js/charts.js" not in text

    # Exactly four occurrences of class="wh-panel"
    assert text.count('class="wh-panel"') == 4
