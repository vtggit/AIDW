from pathlib import Path


def test_issue264_freeform():
    root = Path(__file__).resolve().parents[2]
    html_path = root / "app" / "studio.html"
    text = html_path.read_text()

    # Stylesheets
    assert 'href="css/styles.css"' in text
    assert 'href="css/warehouse.css"' in text

    # Auth & Nav
    assert 'id="auth-status"' in text
    assert 'href="index.html"' in text
    assert 'data-testid="nav-dashboard"' in text

    # Toast
    assert 'id="toast"' in text

    # Control IDs
    ids = [
        "sources-count",
        "source-form",
        "src-name",
        "src-endpoint",
        "src-version",
        "src-submit",
        "sources",
        "inbox-count",
        "inbox",
        "pii-count",
        "pii-inbox",
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
    for uid in ids:
        assert f'id="{uid}"' in text, f'Missing id="{uid}"'

    # Step type options
    assert '<option value="start">' in text
    assert '<option value="end">' in text
    assert '<option value="user">' in text
    assert '<option value="service">' in text
    assert '<option value="gateway">' in text

    # Source version options
    assert '<option value="v4">' in text
    assert '<option value="v2">' in text

    # Script order (strictly increasing string-find positions)
    scripts = [
        "js/config.js",
        "js/auth.js",
        "js/api.js",
        "js/warehouse.js",
        "js/sources.js",
        "js/wizard.js",
    ]
    positions = [text.find(f'src="{s}"') for s in scripts]
    assert all(
        p >= 0 for p in positions
    ), f"Missing script src: {[s for s, p in zip(scripts, positions) if p < 0]}"
    assert all(positions[i] < positions[i + 1] for i in range(len(positions) - 1))

    # Inline init calls occur after the last external script tag
    last_script_pos = max(positions)
    assert text.find("Warehouse.init()", last_script_pos) >= 0
    assert text.find("Sources.init()", last_script_pos) >= 0
    assert text.find("Wizard.init();", last_script_pos) >= 0

    # Negative checks
    assert "js/charts.js" not in text
    assert "<wh-header" not in text
    assert "<wh-main" not in text
    assert "wh-badge" not in text

    # Structural elements
    assert '<header class="wh-header">' in text
    assert '<main class="wh-main">' in text

    # Generate button literal & label
    assert '<button id="wizard-generate"' in text
    assert "Generate diagram" in text

    # Count badges (exact literal prefix, exactly three occurrences)
    badge_prefix = '<span class="badge wh-count" id="'
    assert text.count(badge_prefix) == 3
    for bid in ["sources-count", "inbox-count", "pii-count"]:
        assert f'{badge_prefix}{bid}">' in text

    # Exactly four panels
    assert text.count('class="wh-panel"') == 4
