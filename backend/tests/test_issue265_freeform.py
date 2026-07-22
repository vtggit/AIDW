import pathlib
import re


def test_issue265_freeform():
    js_path = (
        pathlib.Path(__file__).resolve().parents[2] / "app" / "js" / "drilldown.js"
    )
    text = js_path.read_text(encoding="utf-8")

    # const Drilldown present
    assert "const Drilldown" in text

    # each method present followed by ( or :
    for name in ("init", "open", "close", "renderDetail", "_esc", "_fmt"):
        assert re.search(
            rf"\b{name}\s*[\(:]", text
        ), f"{name} not found with correct signature"

    # module.exports guard exporting Drilldown
    assert (
        "module.exports = { Drilldown }" in text or "module.exports={Drilldown}" in text
    )

    # NEVER contains fetch( nor parseInt
    assert "fetch(" not in text, "Must not use bare fetch()"
    assert "parseInt" not in text, "Must not use parseInt"

    # envelope contract literals
    assert ".data" in text
    assert "res.ok" in text

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

    # thousands-separator mechanism
    assert "toLocaleString" in text or "Intl.NumberFormat" in text
