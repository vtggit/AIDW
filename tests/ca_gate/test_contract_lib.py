"""contract-v2 Phase 4a.1 — the vendored contract_lib + the PR-contract skeleton.

Pins the AICRM-side helpers that the (later) merge-gate is built on. Nothing here
enforces a merge yet.
"""
import os
import sys

import pytest

_CA_GATE = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "ca_gate")
sys.path.insert(0, os.path.abspath(_CA_GATE))

import contract_lib  # noqa: E402
import new_pr_contract  # noqa: E402

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "issue_contract_sample.md")


@pytest.fixture
def issue_body():
    with open(_FIXTURE, encoding="utf-8") as fh:
        return fh.read()


def test_normalize_and_hash_are_stable():
    assert contract_lib.normalize_ac_text("  A  B\nC ") == "a b c"
    assert contract_lib.ac_text_hash("X") == contract_lib.ac_text_hash("  x ")
    assert contract_lib.ac_text_hash("a").startswith("sha256:")
    assert contract_lib.ac_text_hash("a") != contract_lib.ac_text_hash("b")


def test_extract_issue_contract(issue_body):
    c = contract_lib.extract_contract_json(issue_body, contract_lib.ISSUE_SCHEMA)
    assert c is not None and c["issue"] == 42
    assert [a["id"] for a in c["acceptance_criteria"]] == ["AC-1", "AC-2", "AC-3"]


def test_skeleton_covers_only_active_acs_with_correct_hashes(issue_body):
    skel = new_pr_contract.build_pr_contract_skeleton(issue_body)
    assert skel["schema"] == "codeagent-pr-contract" and skel["version"] == 1
    assert skel["implements_issue"] == 42
    assert skel["decision_id"] == "D-3"
    assert skel["contract_updated_round"] == 3
    assert skel["governance_seen"] == {"may_proceed": True}
    acs = [e["ac"] for e in skel["proof_map"]]
    assert acs == ["AC-1", "AC-2"]            # retired AC-3 excluded
    for entry in skel["proof_map"]:
        assert entry["kind"] == "proven"
        assert entry["tests"] == ["TODO"]
        assert entry["ac_text_hash"].startswith("sha256:")
    # the hash matches the live AC text (text-change tripwire seed)
    c = contract_lib.extract_contract_json(issue_body, contract_lib.ISSUE_SCHEMA)
    by_id = {a["id"]: a for a in c["acceptance_criteria"]}
    for entry in skel["proof_map"]:
        assert entry["ac_text_hash"] == contract_lib.ac_text_hash(by_id[entry["ac"]]["text"])


def test_rendered_section_round_trips(issue_body):
    section = new_pr_contract.render_pr_section(
        new_pr_contract.build_pr_contract_skeleton(issue_body))
    assert section.startswith("## CodeAgent PR Contract")
    parsed = contract_lib.extract_contract_json(section, contract_lib.PR_SCHEMA)
    assert parsed is not None and parsed["implements_issue"] == 42


def test_skeleton_errors_when_no_contract():
    with pytest.raises(SystemExit):
        new_pr_contract.build_pr_contract_skeleton("# just an issue, no contract\n")
