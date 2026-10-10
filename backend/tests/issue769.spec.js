"""Proof for issue #769, AC-1/AC-2 — collected as pytest nodeid
``tests/issue769.spec.js::issue769 freeform`` by the ``.spec.js``
collector in backend/conftest.py.

The browser proof lives in the same-named Playwright spec
(app/tests/issue769.spec.js); this module proves the same criteria
statically against the app sources, the way the backend freeform tests
do for their frontend specs:

* AC-1  studio.html shows exactly one tool at a time — the panel named
        by ?panel=, or Data sources when the param is absent, unknown,
        or names a panel the user's role hides; every other tool's
        section(s) carry the hidden attribute (Load sequences spans two
        sections and shows both); switching tools is in place
        (pushState, aria-current, scroll reset, the "Studio · <tool
        name>" title, Back/forward); hidden tools keep their DOM and
        state; at 1440x900 the document does not scroll and at 390x844
        there is no horizontal page scroll.
* AC-2  the Playwright spec proves all of that in the browser against
        mocked API responses (no backend), including the non-admin
        (viewer) pass — absent/unknown panels and Feed keys for a
        non-admin all fall back to Data sources — and the superseded
        proofs reach the tool they exercise via ?panel=<tool> (or their
        sidebar item / the default tool) instead of assuming every
        panel is present in the main area at once.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PANELS = (
    "sources",
    "suggestions",
    "pii",
    "wizard",
    "sequences",
    "sequence-runs",
    "retention",
    "ingestion",
    "feedkeys",
    "audit",
)

# The superseded proofs (AC-2): each now reaches the tool it exercises
# via ?panel=<tool> in the URL it opens ...
VIA_PANEL_PARAM = (
    "250_ac_1.spec.js",
    "dashboards.spec.js",
    "suggestions.spec.js",
    "issue389_surgical.spec.js",
    "issue394_surgical.spec.js",
    "issue572.spec.js",
    "issue597_surgical.spec.js",
    "issue598_surgical.spec.js",
    "issue607_surgical.spec.js",
    "issue689.spec.js",
    "issue692.spec.js",
    "issue697_surgical.spec.js",
    "issue767.spec.js",
    "767_ac_3.spec.js",
)
# ... or keeps the default tool (Data sources) / visibility-independent
# module assertions and makes no visibility claim about a non-shown tool.
VIA_DEFAULT_TOOL = (
    "issue568_surgical.spec.js",
    "issue578_surgical.spec.js",
    "issue582_surgical.spec.js",
    "issue588_surgical.spec.js",
    "issue610.spec.js",
    "issue762_surgical.spec.js",
)

PROOF_TITLES = ["issue769 freeform"]


def _read(*parts):
    return (REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def run(title):
    if title != "issue769 freeform":
        raise AssertionError("unknown proof title: %r" % (title,))

    shell = _read("app", "js", "shell.js")
    html = _read("app", "studio.html")
    css = _read("app", "css", "shell.css")
    spec = _read("app", "tests", "issue769.spec.js")

    # ------------------------------------------------------------------
    # AC-1: the shell mechanism — one tool at a time, in-place
    # switching, the page title, the scroll ownership.
    # ------------------------------------------------------------------
    for panel in PANELS:
        assert 'data-panel="%s"' % panel in html, (
            "panel marker missing from studio.html: " + panel
        )
    assert html.count('<section class="wh-panel"') == len(PANELS)
    # ?panel= drives the shown tool; the sidebar switch rewrites it via
    # pushState without a page load; Back/forward (popstate) restore the
    # tool the URL names.
    assert "URLSearchParams(window.location.search).get(\"panel\")" in shell
    assert "history.pushState" in shell
    assert '"popstate"' in shell
    # aria-current="page" and the "Studio · <tool name>" title.
    assert 'setAttribute("aria-current", "page")' in shell
    assert '"Studio · " + tool.label' in shell
    # The main region's scroll resets to the top when the shown tool
    # changes; the document itself never scrolls (the shell's layout).
    assert "region.scrollTop = 0" in shell
    assert "overflow: hidden" in css
    # Load sequences is one tool over two sections (both shown together).
    assert 'sections: ["sequences", "sequence-runs"]' in shell

    # ------------------------------------------------------------------
    # AC-2: the Playwright spec proves the criterion in the browser
    # against mocked API responses (no backend), incl. the non-admin
    # (viewer) pass.
    # ------------------------------------------------------------------
    assert "test('issue769 freeform'" in spec
    assert "test('issue769 freeform (viewer)'" in spec
    # Each ?panel= value shows only its tool (the tools table, with
    # Load sequences spanning both its sections) ...
    assert "sections: ['sequences', 'sequence-runs']" in spec
    assert "'/studio.html?panel=' + tool.name" in spec
    # ... and an absent or unknown panel shows Data sources.
    assert "goto('/studio.html')" in spec
    assert "goto('/studio.html?panel=bogus')" in spec
    # Switching: no page load (a window marker survives), the URL is
    # rewritten, the region scrolls back to the top, the title follows.
    assert "__issue769Marker" in spec
    assert "searchParams.get('panel')" in spec
    assert "scrollTop" in spec
    # Back and Forward restore the previous/next tool, same document.
    assert "goBack()" in spec
    assert "goForward()" in spec
    # A hidden tool keeps its form input across a switch away and back.
    assert "kept source name" in spec
    # Scrolling: no document scroll at 1440x900, no horizontal page
    # scroll at 390x844.
    assert "width: 1440, height: 900" in spec
    assert "width: 390, height: 844" in spec
    # Identity: the non-admin pass boots the production way (the token
    # in the URL hash, the auth endpoints mocked for that user), and an
    # absent or unknown panel — and Feed keys for a non-admin — all
    # show Data sources while the page still renders.
    assert "#access_token=" in spec
    assert "/api/auth/me" in spec
    assert "roles: ['user']" in spec
    assert "?panel=feedkeys" in spec
    assert "Studio · Data sources" in spec
    assert "Signed in · user" in spec

    # ------------------------------------------------------------------
    # AC-2: the superseded proofs change only how they reach the tool
    # they exercise.
    # ------------------------------------------------------------------
    for name in VIA_PANEL_PARAM:
        text = _read("app", "tests", name)
        assert "?panel=" in text, (
            "superseded proof does not reach its tool via ?panel= : " + name
        )
    for name in VIA_DEFAULT_TOOL:
        text = _read("app", "tests", name)
        assert "?panel=" not in text, (
            "expected the default tool (no ?panel=) in: " + name
        )
        # No visibility claim about a tool that is not shown by default:
        # a toBeVisible() may only target the Data sources markup.
        for line in text.splitlines():
            if "toBeVisible(" in line:
                assert "#sources" in line or "src-list" in line or "srcList" in line, (
                    "visibility claim about a non-shown tool in " + name + ": " + line.strip()
                )
