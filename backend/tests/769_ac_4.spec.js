"""Proof for issue #769, AC-3/AC-4 — collected as pytest nodeid
``tests/769_ac_4.spec.js::769_ac_4_data_source`` by the ``.spec.js``
collector in backend/conftest.py.

The browser proof lives in the same-named Playwright spec
(app/tests/769_ac_4.spec.js); this module proves the same criteria
statically against the app sources, the way the backend freeform tests
do for their frontend specs:

* AC-3  the controller hides the FULL panel container — the enclosing
        section.wh-panel of every inactive tool (its header, layout and
        inner [data-panel] content all go with it); Load sequences is
        one tool over two containers.
* AC-4  the shell owns the visibility of the .wh-panel elements: the
        hidden state is re-applied after boot (MutationObserver), and
        css/shell.css keeps an inactive section invisible even when a
        panel's own CSS sets an explicit display value.
* Identity + the review's defect (gated nav item not removed on role
        loss): the role-gated sidebar item is detached fail-closed at
        boot, is put back only while the signed-in user holds the role,
        and LEAVES THE DOM AGAIN when the role is lost — a signature
        watcher runs for the life of the page (no early stop), re-applies
        the gate on every identity/role change, re-resolves the shown
        tool (falling back to Data sources) and hides any section that
        still exposes admin-only content.  The Playwright spec carries
        the browser proof, including the non-admin (viewer) pass booted
        the production way (token in the URL hash, /api/auth/config and
        /api/auth/me mocked) and the role-loss pass (admin logs out, the
        gated item is removed again).
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

PROOF_TITLES = ["769_ac_4_data_source"]


def _read(*parts):
    return (REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def run(title):
    if title != "769_ac_4_data_source":
        raise AssertionError("unknown proof title: %r" % (title,))

    shell = _read("app", "js", "shell.js")
    css = _read("app", "css", "shell.css")
    html = _read("app", "studio.html")
    spec = _read("app", "tests", "769_ac_4.spec.js")

    # ------------------------------------------------------------------
    # AC-3: the controller hides the FULL panel container (the enclosing
    # section.wh-panel), never just the inner [data-panel] marker.
    # ------------------------------------------------------------------
    assert 'closest("section.wh-panel")' in shell, (
        "the shell must resolve each panel's enclosing section.wh-panel"
    )
    assert 'setAttribute("hidden", "")' in shell, (
        "the shell must set the hidden attribute on the inactive container"
    )
    assert 'removeAttribute("hidden")' in shell, (
        "the shell must clear the hidden attribute on the shown container"
    )
    for panel in PANELS:
        assert 'data-panel="%s"' % panel in html, (
            "panel marker missing from studio.html: " + panel
        )
    assert html.count('<section class="wh-panel"') == len(PANELS), (
        "studio.html must carry one section.wh-panel container per panel, got %d"
        % html.count('<section class="wh-panel"')
    )
    # Load sequences is one tool over two containers.
    assert 'sections: ["sequences", "sequence-runs"]' in shell, (
        "Load sequences must span both its sections"
    )

    # ------------------------------------------------------------------
    # AC-4: the shell owns the visibility — enforced after boot (a module
    # that drifts the hidden state is corrected) and kept invisible by
    # the shell's CSS even against an explicit panel display value.
    # ------------------------------------------------------------------
    assert "new MutationObserver" in shell, (
        "the shell must re-apply the hidden state after boot"
    )
    assert 'attributeFilter: ["hidden"]' in shell, (
        "the observer must watch the hidden attribute"
    )
    assert "display: none !important" in css, (
        "shell.css must force-hide inactive sections against explicit display values"
    )
    assert "main.wh-main > .wh-panel[hidden]" in css, (
        "shell.css must scope the force-hide to the Studio's .wh-panel sections"
    )

    # ------------------------------------------------------------------
    # Role-gated sidebar item: fail-closed at boot, present only while
    # the role is held, and removed AGAIN when the role is lost (the
    # review's defect).  The gate is re-applied by a watcher that runs
    # for the life of the page — no early stop after auth settled — and
    # a role loss re-resolves the shown tool and hides any section that
    # still exposes admin-only content.
    # ------------------------------------------------------------------
    assert "_detachGatedItems" in shell, (
        "the shell must detach the role-gated sidebar item(s) fail-closed at boot"
    )
    assert "rec.el.remove()" in shell, (
        "the gate must be bidirectional: the item leaves the DOM again on role loss"
    )
    assert "_authSignature" in shell, (
        "the watcher must compare identity/role state to detect a change"
    )
    assert "clearInterval" not in shell, (
        "the auth watcher must not stop: a role loss happens AFTER auth settled"
    )
    assert "_sectionExposesGatedContent" in shell, (
        "a role loss must hide a section that still exposes admin-only content"
    )
    assert 'querySelector("[data-requires-role]")' in shell
    assert "!this._toolUsable(active)" in shell, (
        "the shown tool must be re-resolved when the role no longer covers it"
    )

    # ------------------------------------------------------------------
    # The Playwright spec carries the browser proof: the admin pass
    # (AC-3/AC-4 incl. the explicit-display overrides), the non-admin
    # (viewer) pass booted the production way, and the role-loss pass.
    # ------------------------------------------------------------------
    assert "test('769_ac_4_data_source'" in spec
    assert "test('769_ac_4_data_source (viewer)'" in spec
    # Identity: the page boots the production way for a role 'user' —
    # the token in the URL hash, the auth endpoints mocked for that user,
    # the hash token reaching /api/auth/me as a Bearer header.
    assert "#access_token=" in spec
    assert "/api/auth/config" in spec
    assert "/api/auth/me" in spec
    assert "Bearer " in spec
    assert "roles: ['user']" in spec
    # ...while the page still renders and the admin-only controls are absent.
    assert "Signed in · user" in spec
    assert "toHaveCount(0)" in spec
    # AC-4 in the browser: an explicit inline display and a panel
    # stylesheet with explicit display values do not unhide an inactive
    # section.
    assert "style.display = 'block'" in spec
    assert "display: block" in spec
    # The role-loss proof: the gated item is present for the admin, the
    # role is lost (the admin logs out), and the item is removed again —
    # no role-gated sidebar element survives, the shown tool falls back
    # to Data sources, and the Feed keys section is hidden.
    assert "Auth.logout()" in spec
    assert "Studio · Data sources" in spec
    assert "expectSectionHidden(page, 'feedkeys')" in spec
