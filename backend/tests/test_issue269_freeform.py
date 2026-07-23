"""Slim index.html — the dashboard-first operations surface (Issue #269).

Static invariants: the page carries ONLY the dashboard and the drill-down panel, loads the
six operations scripts in order, and contains NONE of the configuration controls that moved
to studio.html (#264). Pure string membership assertions, no f-strings.
"""

from pathlib import Path


def test_issue269_freeform():
    repo_root = Path(__file__).resolve().parents[2]
    html = (repo_root / "app" / "index.html").read_text(encoding="utf-8")

    for needle in [
        "<!doctype html>",
        'href="css/styles.css"',
        'href="css/warehouse.css"',
        "<title>AIDW — AI Data Warehouse</title>",
        'id="auth-status"',
        'href="studio.html"',
        'data-testid="nav-studio"',
        "<h2>Dashboards</h2>",
        'id="dashboards"',
        'id="drilldown"',
        'id="drilldown-close"',
        'id="drilldown-body"',
        'id="toast"',
    ]:
        assert needle in html, "missing required content: " + needle

    # exactly two panel SECTIONS: dashboards + the drill-down panel.
    # (match the <section> tag, not a bare `wh-panel` prefix — that would also count
    # the `wh-panel-head` div inside the dashboards section.)
    assert (
        html.count('<section class="wh-panel') == 2
    ), "expected exactly 2 wh-panel sections"

    # the six operations scripts, in order, drilldown last, charts before warehouse
    scripts = [
        "js/config.js",
        "js/auth.js",
        "js/api.js",
        "js/charts.js",
        "js/warehouse.js",
        "js/drilldown.js",
    ]
    prev = -1
    for src in scripts:
        pos = html.find(src)
        assert pos > prev, "script out of order or missing: " + src
        prev = pos

    dc = html.find("DOMContentLoaded")
    assert dc >= 0, "DOMContentLoaded handler missing"
    tail = html[dc:]
    assert "Warehouse.init();" in tail, "Warehouse.init() missing from handler"
    assert "Drilldown.init();" in tail, "Drilldown.init() missing from handler"

    # configuration controls moved to studio.html — none may remain here
    for forbidden in [
        "js/sources.js",
        "js/wizard.js",
        "source-form",
        "src-name",
        "src-endpoint",
        "src-version",
        "src-submit",
        "sources-count",
        'id="sources"',
        "inbox",
        "pii-count",
        "pii-inbox",
        "wizard-",
        "Sources.init",
        "Wizard.init",
    ]:
        assert forbidden not in html, "forbidden (moved to studio.html): " + forbidden
