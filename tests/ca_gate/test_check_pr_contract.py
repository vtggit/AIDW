"""contract-v2 Phase 4a.3 — the merge-gate checker verdict logic.

Drives the pure ``evaluate()`` core through the eight scenarios from the design's
#128 validation plan, plus the junitxml parser and the AST assertion-floor.
"""
import json
import os
import sys
import textwrap

import pytest

_CA_GATE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "ca_gate"))
sys.path.insert(0, _CA_GATE)

import check_pr_contract as chk  # noqa: E402
import contract_lib  # noqa: E402

ACS = [
    {"id": "AC-1", "text": "do X", "status": "active", "checked": False, "retired_round": None},
    {"id": "AC-2", "text": "do Y", "status": "active", "checked": False, "retired_round": None},
    {"id": "AC-3", "text": "old", "status": "retired", "checked": False, "retired_round": 2},
]


def issue_contract(may_proceed=True, decision="D-3", acs=ACS, blockers=None):
    return {
        "schema": "codeagent-contract", "version": 1, "issue": 42, "updated_round": 3,
        "decision": {"id": decision},
        "acceptance_criteria": acs,
        "governance": {"may_proceed": may_proceed,
                       "resolution_state": "completed" if may_proceed else "pending",
                       "blockers": blockers or []},
        "open_questions_panel": [], "open_questions_author": [],
        "next_id": {"ac": 4, "oq": 1, "aq": 1},
    }


def entry(ac, text, nodeids):
    return {"ac": ac, "ac_text_hash": contract_lib.ac_text_hash(text),
            "tests": [{"nodeid": n} for n in nodeids], "kind": "proven"}


def pr_body(proof_map, implements=42, decision="D-3", note="Implements: #42"):
    pr = {"schema": "codeagent-pr-contract", "version": 1, "implements_issue": implements,
          "decision_id": decision, "contract_updated_round": 3,
          "governance_seen": {"may_proceed": True}, "proof_map": proof_map}
    return note + "\n\n## CodeAgent PR Contract\n<details>\n\n```json\n" + json.dumps(pr) + "\n```\n</details>"


JUNIT = {"passed": {"t::a", "t::b"}, "present": {"t::a", "t::b"}, "skipped": set()}
ALL_OK = lambda n: True


def _eval(body, ic, junit=JUNIT, nontrivial=ALL_OK):
    return chk.evaluate(body, ic, chk.extract_prose_issue_links(body), junit, nontrivial)


def _happy_pm():
    return [entry("AC-1", "do X", ["t::a"]), entry("AC-2", "do Y", ["t::b"])]


# ── 8 scenarios ──

def test_happy_passes():
    r = _eval(pr_body(_happy_pm()), issue_contract())
    assert r.ok and not r.fail_open
    assert {row["result"] for row in r.ac_rows} == {"OK"}


def test_missing_proof_fails():
    r = _eval(pr_body([entry("AC-1", "do X", ["t::a"])]), issue_contract())
    assert not r.ok and any("AC-2" in f for f in r.failures)


def test_stale_decision_fails():
    r = _eval(pr_body(_happy_pm(), decision="D-2"), issue_contract(decision="D-3"))
    assert not r.ok and any("stale decision" in f for f in r.failures)


def test_text_changed_fails():
    pm = [entry("AC-1", "DIFFERENT TEXT", ["t::a"]), entry("AC-2", "do Y", ["t::b"])]
    r = _eval(pr_body(pm), issue_contract())
    assert not r.ok and any("AC-1" in f and "hash" in f for f in r.failures)


def test_trivial_test_fails():
    r = _eval(pr_body(_happy_pm()), issue_contract(), nontrivial=lambda n: n != "t::a")
    assert not r.ok and any("AC-1" in f and "trivial" in f for f in r.failures)


def test_governance_pending_fails():
    r = _eval(pr_body(_happy_pm()), issue_contract(may_proceed=False))
    assert not r.ok and any("governance not green" in f for f in r.failures)


def test_fail_open_when_no_contract_and_no_link():
    r = _eval("Just a normal PR.\n\n## Summary\nstuff\n", None)
    assert r.fail_open and r.ok is True


def test_strip_dodge_fails_closed():
    # links a contracted issue but omits the PR contract
    r = _eval("Implements: #42\n\n## Summary\nno contract block here\n", issue_contract())
    assert not r.ok and any("proof-map required" in f for f in r.failures)


def test_multi_issue_strip_dodge_fails_closed():
    # PR links a non-contracted issue (#7) AND a contracted one — any_contracted
    # must drive the verdict, not just the lowest-numbered linked issue.
    body = "Relates to #7\n\n## Summary\nno contract block\n"
    r = chk.evaluate(body, None, {7}, JUNIT, ALL_OK, any_contracted=True)
    assert not r.ok and any("proof-map required" in f for f in r.failures)
    # genuinely no contracted link -> fail-open
    r2 = chk.evaluate(body, None, {7}, JUNIT, ALL_OK, any_contracted=False)
    assert r2.fail_open and r2.ok


# ── extra edges ──

def test_not_collected_test_fails():
    pm = [entry("AC-1", "do X", ["t::missing"]), entry("AC-2", "do Y", ["t::b"])]
    r = _eval(pr_body(pm), issue_contract())
    assert not r.ok and any("not collected" in f for f in r.failures)


def test_skipped_test_does_not_prove():
    junit = {"passed": {"t::b"}, "present": {"t::a", "t::b"}, "skipped": {"t::a"}}
    r = _eval(pr_body(_happy_pm()), issue_contract(), junit=junit)
    assert not r.ok and any("AC-1" in f and "did not pass" in f for f in r.failures)


def test_implements_link_mismatch_fails():
    r = _eval(pr_body(_happy_pm(), implements=99, note="Implements: #42"), issue_contract())
    assert not r.ok and any("does not match" in f for f in r.failures)


def test_retired_ac_not_required_and_warned_if_referenced():
    pm = _happy_pm() + [entry("AC-3", "old", ["t::a"])]
    r = _eval(pr_body(pm), issue_contract())
    assert r.ok                                    # AC-3 retired -> not required
    assert any("AC-3" in w for w in r.warnings)    # referenced -> advisory warn


# ── helpers ──

def test_parametrized_failure_makes_base_not_passed(tmp_path):
    xml = ('<testsuite>'
           '<testcase classname="tests.test_x" name="test_y[a]" file="tests/test_x.py"/>'
           '<testcase classname="tests.test_x" name="test_y[b]" file="tests/test_x.py"><failure/></testcase>'
           '</testsuite>')
    (tmp_path / "j.xml").write_text(xml)
    j = chk.parse_junit(str(tmp_path / "j.xml"))
    assert "tests/test_x.py::test_y" in j["present"]
    assert "tests/test_x.py::test_y" in j["failed"]
    assert "tests/test_x.py::test_y" not in j["passed"]   # one case failed -> base not passed


def test_parametrized_proof_map_matches_base():
    # an author writing the [case] variant still matches the base junit nodeid
    junit = {"passed": {"tests/x.py::test_y"}, "present": {"tests/x.py::test_y"}, "skipped": set()}
    ic = issue_contract(acs=[{"id": "AC-1", "text": "do X", "status": "active",
                              "checked": False, "retired_round": None}])
    pm = [entry("AC-1", "do X", ["tests/x.py::test_y[case-1]"])]
    r = chk.evaluate(pr_body(pm), ic, {42}, junit, ALL_OK)
    assert r.ok


def test_duplicate_ac_entry_warns():
    pm = [entry("AC-1", "do X", ["t::a"]), entry("AC-1", "do X", ["t::a"]),
          entry("AC-2", "do Y", ["t::b"])]
    r = _eval(pr_body(pm), issue_contract())
    assert r.ok and any("duplicate" in w for w in r.warnings)


def test_nodeid_from_file_attr_module_and_class():
    # module-level test: classname == module path, stem matches -> no class
    assert chk._nodeid_from("tests/test_x.py", "tests.test_x", "test_a") \
        == "tests/test_x.py::test_a"
    # class-based test: trailing CapWords segment is the class
    assert chk._nodeid_from("tests/sub/test_x.py", "tests.sub.test_x.TestK", "test_a[p]") \
        == "tests/sub/test_x.py::TestK::test_a"


def test_extract_prose_issue_links():
    assert chk.extract_prose_issue_links("Implements: #12\nalso Closes #34") == {12, 34}
    assert chk.extract_prose_issue_links("no links") == set()


def test_parse_junit(tmp_path):
    xml = """<testsuite>
      <testcase classname="tests.test_x" name="test_a"/>
      <testcase classname="tests.test_x" name="test_b"><failure/></testcase>
      <testcase classname="tests.test_x" name="test_c"><skipped/></testcase>
      <testcase classname="tests.test_x.TestK" name="test_d"/>
    </testsuite>"""
    p = tmp_path / "j.xml"; p.write_text(xml)
    j = chk.parse_junit(str(p))
    assert "tests/test_x.py::test_a" in j["passed"]
    assert "tests/test_x.py::test_b" not in j["passed"]
    assert "tests/test_x.py::test_c" in j["skipped"]
    assert "tests/test_x.py::TestK::test_d" in j["passed"]


def test_ast_assertion_floor(tmp_path):
    src = textwrap.dedent('''
        def test_trivial_pass():
            pass
        def test_assert_true():
            assert True
        def test_real():
            x = 1 + 1
            assert x == 2
        def test_raises():
            import pytest
            with pytest.raises(ValueError):
                int("x")
        def test_helper():
            assert_response_ok(resp)
    ''')
    (tmp_path / "tests").mkdir()
    f = tmp_path / "tests" / "test_z.py"; f.write_text(src)
    root = str(tmp_path)
    assert chk.ast_test_is_nontrivial(root, "tests/test_z.py::test_trivial_pass") is False
    assert chk.ast_test_is_nontrivial(root, "tests/test_z.py::test_assert_true") is False
    assert chk.ast_test_is_nontrivial(root, "tests/test_z.py::test_real") is True
    assert chk.ast_test_is_nontrivial(root, "tests/test_z.py::test_raises") is True
    assert chk.ast_test_is_nontrivial(root, "tests/test_z.py::test_helper") is True
    # unknown file/func -> lenient True (report-only, don't false-fail)
    assert chk.ast_test_is_nontrivial(root, "tests/nope.py::test_x") is True


def _issue_body(ic):
    return "# Issue\n\n## CodeAgent Contract\n```json\n" + json.dumps(ic) + "\n```\n"


def test_cli_report_only_end_to_end(tmp_path, monkeypatch, capsys):
    pm = [entry("AC-1", "do X", ["tests/test_x.py::test_a"]),
          entry("AC-2", "do Y", ["tests/test_x.py::test_b"])]
    (tmp_path / "pr.md").write_text(pr_body(pm), encoding="utf-8")
    (tmp_path / "r.xml").write_text(
        '<testsuite>'
        '<testcase classname="tests.test_x" name="test_a"/>'
        '<testcase classname="tests.test_x" name="test_b"/>'
        '</testsuite>', encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "def test_a():\n    assert 1 == 1\ndef test_b():\n    assert 2 == 2\n", encoding="utf-8")
    monkeypatch.setattr(chk, "fetch_issue_body", lambda repo, n: _issue_body(issue_contract()))
    rc = chk.main([
        "--pr-body-file", str(tmp_path / "pr.md"),
        "--junit", str(tmp_path / "r.xml"),
        "--repo-root", str(tmp_path),
        "--report-only",
    ])
    assert rc == 0                                  # report-only never blocks
    assert "PASS" in capsys.readouterr().out


def test_cli_report_only_exits_zero_even_on_fail(tmp_path, monkeypatch, capsys):
    # missing proof for AC-2 -> would FAIL, but report-only still exits 0
    (tmp_path / "pr.md").write_text(pr_body([entry("AC-1", "do X", ["tests/test_x.py::test_a"])]),
                                    encoding="utf-8")
    (tmp_path / "r.xml").write_text(
        '<testsuite><testcase classname="tests.test_x" name="test_a"/></testsuite>', encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_a():\n    assert 1\n", encoding="utf-8")
    monkeypatch.setattr(chk, "fetch_issue_body", lambda repo, n: _issue_body(issue_contract()))
    rc = chk.main([
        "--pr-body-file", str(tmp_path / "pr.md"), "--junit", str(tmp_path / "r.xml"),
        "--repo-root", str(tmp_path), "--report-only",
    ])
    assert rc == 0
    assert "would FAIL" in capsys.readouterr().out


# ── P4a.4: changed-files binding + enforcing exit codes ──

_TWO = [{"id": "AC-1", "text": "do X", "status": "active", "checked": False, "retired_round": None},
        {"id": "AC-2", "text": "do Y", "status": "active", "checked": False, "retired_round": None}]
_JUNIT2 = {"passed": {"tests/test_x.py::test_a", "tests/test_y.py::test_b"},
           "present": {"tests/test_x.py::test_a", "tests/test_y.py::test_b"}, "skipped": set()}


def _pm2():
    return [entry("AC-1", "do X", ["tests/test_x.py::test_a"]),
            entry("AC-2", "do Y", ["tests/test_y.py::test_b"])]


def test_changed_files_binding_requires_test_in_diff():
    ic = issue_contract(acs=_TWO)
    r = chk.evaluate(pr_body(_pm2()), ic, {42}, _JUNIT2, ALL_OK,
                     changed_files={"tests/test_x.py"})   # test_y.py NOT in the diff
    assert not r.ok and any("AC-2" in f and "not added/modified" in f for f in r.failures)
    r2 = chk.evaluate(pr_body(_pm2()), ic, {42}, _JUNIT2, ALL_OK,
                      changed_files={"tests/test_x.py", "tests/test_y.py"})
    assert r2.ok


def test_changed_files_none_skips_binding():
    r = chk.evaluate(pr_body(_pm2()), issue_contract(acs=_TWO), {42}, _JUNIT2, ALL_OK,
                     changed_files=None)
    assert r.ok                                    # no diff provided -> binding off


def test_cli_enforcing_exits_nonzero_on_fail(tmp_path, monkeypatch, capsys):
    (tmp_path / "pr.md").write_text(pr_body([entry("AC-1", "do X", ["tests/test_x.py::test_a"])]),
                                    encoding="utf-8")
    (tmp_path / "r.xml").write_text(
        '<testsuite><testcase classname="tests.test_x" name="test_a" file="tests/test_x.py"/></testsuite>',
        encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_a():\n    assert 1\n", encoding="utf-8")
    monkeypatch.setattr(chk, "fetch_issue_body", lambda repo, n: _issue_body(issue_contract()))
    # AC-2 unproven; no --report-only -> enforcing -> non-zero exit
    rc = chk.main(["--pr-body-file", str(tmp_path / "pr.md"), "--junit", str(tmp_path / "r.xml"),
                   "--repo-root", str(tmp_path)])
    assert rc == 1


def test_cli_strips_repo_root_prefix_from_junit_nodeids(tmp_path, monkeypatch, capsys):
    """When pytest's rootdir is the repo root, a backend test collects as
    ``backend/tests/x.py::t``. The proof-map is backend-relative (``tests/x.py::t``),
    so main() must strip the --repo-root prefix from junit nodeids — else every
    mapped test reads as "not collected" (the bug the first live P4b.0 run hit)."""
    pm = [entry("AC-1", "do X", ["tests/test_x.py::test_a"]),
          entry("AC-2", "do Y", ["tests/test_x.py::test_b"])]
    (tmp_path / "pr.md").write_text(pr_body(pm), encoding="utf-8")
    (tmp_path / "r.xml").write_text(
        '<testsuite>'
        '<testcase classname="backend.tests.test_x" name="test_a"/>'
        '<testcase classname="backend.tests.test_x" name="test_b"/>'
        '</testsuite>', encoding="utf-8")
    monkeypatch.setattr(chk, "fetch_issue_body", lambda repo, n: _issue_body(issue_contract()))
    rc = chk.main(["--pr-body-file", str(tmp_path / "pr.md"), "--junit", str(tmp_path / "r.xml"),
                   "--repo-root", "backend", "--report-only"])
    out = capsys.readouterr().out
    assert rc == 0 and "PASS" in out and "not collected" not in out
