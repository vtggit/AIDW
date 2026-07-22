import re
from pathlib import Path


def test_issue265_freeform():
    repo_root = Path(__file__).resolve().parents[2]
    js_path = repo_root / "app" / "js" / "drilldown.js"
    text = js_path.read_text()

    # const Drilldown present
    assert "const Drilldown" in text, "Missing `const Drilldown` declaration"

    # Each of the seven method names followed by ( or :
    for name in ["init", "open", "close", "renderDetail", "_fail", "_esc", "_fmt"]:
        pattern = rf"{name}\s*[\(:]"
        assert re.search(pattern, text), f"Missing method `{name}`"

    # module.exports guard present
    assert "module.exports = { Drilldown }" in text, "Missing CommonJS export guard"

    # Forbidden patterns must NOT appear
    forbidden = ["fetch(", "parseInt", "style.display", "createElement", "{ dimension:"]
    for token in forbidden:
        assert token not in text, f"Should not contain `{token}`"

    # Required tokens MUST appear
    required = [
        "res.ok",
        ".data",
        "hidden = false",
        "hidden = true",
        "/dashboard-items",
        "/data",
        "drilldown-body",
        "drilldown-close",
        "dashboards",
        "wh-item",
        "data-id",
        "Charts.renderBar",
        "measure_label",
        "total_rows",
        "refreshed_at",
        "dd-table",
        "drilldown-table",
        "\u2014",  # em dash —
    ]
    for token in required:
        assert token in text, f"Should contain `{token}`"

    # Thousands-separator mechanism present
    has_formatter = "toLocaleString" in text or "Intl.NumberFormat" in text
    assert (
        has_formatter
    ), "Missing thousands-separator mechanism (toLocaleString or Intl.NumberFormat)"

    # _fail must occur at least three times
    fail_count = text.count("_fail")
    assert fail_count >= 3, f"_fail appears {fail_count} time(s), expected at least 3"
