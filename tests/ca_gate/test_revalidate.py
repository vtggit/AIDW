"""contract-v2 Phase 4a.4 — the daily re-validation issue-side core."""
import os
import sys

_CA_GATE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "ca_gate"))
sys.path.insert(0, _CA_GATE)

import contract_lib  # noqa: E402
import revalidate  # noqa: E402


def _ic(may_proceed=True, decision="D-3", acs=None):
    acs = acs or [{"id": "AC-1", "text": "do X", "status": "active", "checked": False, "retired_round": None}]
    return {"schema": "codeagent-contract", "decision": {"id": decision},
            "acceptance_criteria": acs,
            "governance": {"may_proceed": may_proceed,
                           "resolution_state": "completed" if may_proceed else "pending",
                           "blockers": []}}


def _prc(decision="D-3", acs=None):
    acs = acs or [{"id": "AC-1", "text": "do X"}]
    return {"schema": "codeagent-pr-contract", "implements_issue": 42, "decision_id": decision,
            "proof_map": [{"ac": a["id"], "ac_text_hash": contract_lib.ac_text_hash(a["text"]),
                           "tests": [{"nodeid": "t::a"}], "kind": "proven"} for a in acs]}


def test_revalidate_ok():
    c, reasons = revalidate.revalidate_issue_side(_prc(), _ic())
    assert c == "success" and not reasons


def test_revalidate_governance_veto():
    c, reasons = revalidate.revalidate_issue_side(_prc(), _ic(may_proceed=False))
    assert c == "failure" and any("governance" in r for r in reasons)


def test_revalidate_stale_decision():
    c, reasons = revalidate.revalidate_issue_side(_prc(decision="D-2"), _ic(decision="D-3"))
    assert c == "failure" and any("stale decision" in r for r in reasons)


def test_revalidate_text_changed():
    c, reasons = revalidate.revalidate_issue_side(
        _prc(acs=[{"id": "AC-1", "text": "do X"}]),
        _ic(acs=[{"id": "AC-1", "text": "do X DIFFERENT", "status": "active",
                  "checked": False, "retired_round": None}]))
    assert c == "failure" and any("text changed" in r for r in reasons)


def test_revalidate_neutral_when_issue_uncontracted():
    c, reasons = revalidate.revalidate_issue_side(_prc(), None)
    assert c == "neutral"
