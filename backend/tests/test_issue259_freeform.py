"""Static contract verification for app/js/charts.js (Issue #259)."""

import re
from pathlib import Path


def test_issue259_freeform():
    repo_root = Path(__file__).resolve().parents[2]
    charts_path = repo_root / "app" / "js" / "charts.js"
    text = charts_path.read_text(encoding="utf-8")

    # const Charts present
    assert "const Charts" in text, "Missing 'const Charts'"

    # Each of the four export names present followed by ( or :
    for name in ("renderBar", "renderKpi", "_esc", "_fmt"):
        pattern = rf"{re.escape(name)}\s*[\(\:]"
        assert re.search(pattern, text), f"Missing '{name}' export signature"

    # module.exports guard exporting Charts
    assert "module.exports" in text, "Missing module.exports guard"
    exports_match = re.search(r"module\.exports\s*=\s*\{[^}]*\}", text)
    assert exports_match is not None, "module.exports must export an object literal"
    assert "Charts" in exports_match.group(0), "module.exports must export Charts"

    # Forbidden patterns — pure string builders only
    for forbidden in ("fetch(", "document.", "window.", "Date.now", "Math.random"):
        assert forbidden not in text, f"Forbidden pattern found: {forbidden}"

    # Required SVG literals
    for literal in ("<svg", "viewBox", "<rect", "<title>", "Other"):
        assert literal in text, f"Missing required literal: {literal}"

    # Thousands-separator mechanism present
    has_thousands = (
        "toLocaleString" in text
        or "Intl.NumberFormat" in text
        or r"\B(?=(\d{3})+(?!\d))" in text
    )
    assert has_thousands, "Missing thousands-separator mechanism"

    # Escape helper handles at least &, <, and "
    esc_idx = text.index("_esc")
    esc_context = text[esc_idx : esc_idx + 500]
    assert "&amp;" in esc_context or "/&/" in esc_context, "_esc must handle &"
    assert "&lt;" in esc_context or "/</" in esc_context, "_esc must handle <"
    assert "&quot;" in esc_context or '/"/' in esc_context, '_esc must handle "'
