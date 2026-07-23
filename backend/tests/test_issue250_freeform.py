"""Migration verification for the wizard's move off index.html (Issues #250 → #264/#269).

ORIGINALLY (issue #250) this proved the wizard was wired INTO app/index.html. That design was
superseded: #264 moved the wizard and every configuration panel to app/studio.html, and #269
slimmed index.html to the dashboard-first operations surface. The old index.html assertions
were therefore RETIRED — they tested a design that no longer exists — and this test now proves
the MIGRATION instead: the wizard lives in studio.html (also proven by test_issue264_freeform),
index.html no longer carries it, and the Playwright spec targets the wizard's new home.
"""

from pathlib import Path


def test_issue250_freeform():
    repo_root = Path(__file__).resolve().parents[2]
    studio = (repo_root / "app" / "studio.html").read_text(encoding="utf-8")
    index = (repo_root / "app" / "index.html").read_text(encoding="utf-8")
    spec = (repo_root / "app" / "tests" / "250_ac_1.spec.js").read_text(
        encoding="utf-8"
    )

    # the wizard's controls now live in studio.html
    for wid in [
        "wizard-definitions",
        "wizard-generate",
        "wizard-svg",
        "wizard-step-type",
        "wizard-flow-source",
        "wizard-flow-target",
    ]:
        assert 'id="' + wid + '"' in studio, (
            "wizard control missing from studio.html: " + wid
        )

    # ...and no longer in index.html (the operations surface)
    for gone in ["wizard-", "source-form", 'id="sources"']:
        assert gone not in index, "configuration control still in index.html: " + gone

    # the Playwright spec still drives the wizard flow, now against studio.html
    for token in [
        "test(",
        "data-testid",
        "wizard-definitions",
        "wizard-generate",
        "wizard-svg",
        "BASE_URL",
        "studio.html",
    ]:
        assert token in spec, "missing token in spec: " + token
