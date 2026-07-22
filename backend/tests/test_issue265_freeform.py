import re
from pathlib import Path


def test_issue265_freeform():
    repo_root = Path(__file__).resolve().parents[2]
    js_path = repo_root / "app" / "js" / "drilldown.js"
    text = js_path.read_text(encoding="utf-8")

    # const Drilldown present
    assert "const Drilldown" in text

    # each method present followed by ( or :
    for name in ("init", "open", "close", "renderDetail", "_esc", "_fmt"):
        pattern = rf"{name}\s*[\(:]"
        assert re.search(pattern, text), f"{name} not found followed by ( or :"

    # module.exports guard exporting Drilldown
    assert "module.exports" in text
    assert "{ Drilldown }" in text or "Drilldown," in text

    # NEVER contains fetch( nor parseInt
    assert "fetch(" not in text, "Must not use fetch()"
    assert "parseInt" not in text, "Must not use parseInt"

    # envelope contract
    assert ".data" in text, "Missing .data access"
    assert "res.ok" in text, "Missing res.ok check"

    # required literals
    for lit in (
        "/dashboard-items",
        "/data",
        "drilldown",
        "drilldown-body",
        "drilldown-close",
        "dashboards",
        "wh-item",
        "data-id",
        "Charts.renderBar",
        "dd-table",
        "drilldown-table",
    ):
        assert lit in text, f"Missing literal: {lit}"

    # meta keys that renderBar actually reads
    for key in ("measure_label", "total_rows", "refreshed_at"):
        assert key in text, f"Missing meta key: {key}"

    # _fail occurs at least three times (definition + both call sites)
    assert text.count("_fail") >= 3, "_fail must appear at least 3 times"

    # em dash literal for null/undefined/NaN formatting
    assert "\u2014" in text or "—" in text, "Missing em dash literal —"

    # does NOT contain { dimension: (renderBar ignores it)
    assert "{ dimension:" not in text, "Must not use { dimension: key"

    # thousands-separator mechanism present
    assert (
        "toLocaleString" in text or "Intl.NumberFormat" in text
    ), "Missing thousands-separator mechanism"
