"""Self-tests for the merge-gate's proving-nodeid lister (report-only step)."""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "ca_gate")
)

from list_proof_nodeids import proof_nodeids  # noqa: E402


def _body(proof_map_json: str) -> str:
    return (
        "Some PR description.\n\n"
        "```json\n"
        '{"schema": "codeagent-pr-contract", "implements_issue": 42, '
        f'"proof_map": {proof_map_json}}}\n'
        "```\n"
    )


def test_extracts_dict_and_string_tests_dedup_order():
    body = _body(
        '[{"ac": "AC-1", "kind": "proven", '
        '"tests": [{"nodeid": "tests/test_a.py::test_one"}, "tests/test_b.py::test_two"]},'
        '{"ac": "AC-2", "kind": "proven", '
        '"tests": ["tests/test_a.py::test_one", "tests/test_c.py::test_three"]}]'
    )
    # first-seen order; the AC-2 duplicate of test_one is dropped
    assert proof_nodeids(body) == [
        "tests/test_a.py::test_one",
        "tests/test_b.py::test_two",
        "tests/test_c.py::test_three",
    ]


def test_filters_todo_and_none():
    body = _body(
        '[{"ac": "AC-1", "kind": "proven", '
        '"tests": ["TODO", {"nodeid": null}, "tests/test_real.py::test_x"]}]'
    )
    assert proof_nodeids(body) == ["tests/test_real.py::test_x"]


def test_strips_parametrization_to_base_and_collapses():
    body = _body(
        '[{"ac": "AC-1", "kind": "proven", '
        '"tests": ["tests/x.py::t[a]", "tests/x.py::t[b]", "tests/y.py::u"]}]'
    )
    # [a] and [b] both collapse to the single base tests/x.py::t (pytest runs all params)
    assert proof_nodeids(body) == ["tests/x.py::t", "tests/y.py::u"]


def test_no_pr_contract_returns_empty():
    assert proof_nodeids("a plain PR body, no contract block") == []


def test_empty_proof_map_returns_empty():
    assert proof_nodeids(_body("[]")) == []
