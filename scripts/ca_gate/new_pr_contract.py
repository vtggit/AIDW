"""Generate a codeagent-pr-contract skeleton from an issue's contract (offline).

Usage:
    python scripts/ca_gate/new_pr_contract.py --issue-body-file issue.md [--issue N]
    gh issue view 128 --json body -q .body | python scripts/ca_gate/new_pr_contract.py

Reads an issue body that carries a ``codeagent-contract`` footer, and prints a
``## CodeAgent PR Contract`` section with one ``proof_map`` entry per ACTIVE
acceptance criterion — each with its ``ac_text_hash`` filled in and
``tests: ["TODO"]`` for you to replace with the pytest nodeids that prove it.
Nothing here enforces anything; that's the CI merge-gate (a later phase).
"""
from __future__ import annotations

import argparse
import json
import sys

from contract_lib import ISSUE_SCHEMA, ac_text_hash, extract_contract_json


def build_pr_contract_skeleton(issue_body: str, issue_number: int | None = None) -> dict:
    issue = extract_contract_json(issue_body, ISSUE_SCHEMA)
    if issue is None:
        raise SystemExit("error: no codeagent-contract block found in the issue body")
    active = [
        ac for ac in (issue.get("acceptance_criteria") or [])
        if ac.get("status") == "active"
    ]
    decision = issue.get("decision") or {}
    governance = issue.get("governance") or {}
    return {
        "schema": "codeagent-pr-contract",
        "version": 1,
        "implements_issue": issue_number or issue.get("issue"),
        "decision_id": decision.get("id"),
        "contract_updated_round": issue.get("updated_round"),
        "governance_seen": {"may_proceed": governance.get("may_proceed")},
        "proof_map": [
            {
                "ac": ac["id"],
                "ac_text_hash": ac_text_hash(ac.get("text", "")),
                "tests": ["TODO"],
                "kind": "proven",
            }
            for ac in active
        ],
    }


def render_pr_section(contract: dict) -> str:
    payload = json.dumps(contract, indent=2, sort_keys=True)
    return (
        "## CodeAgent PR Contract\n"
        "<!-- codeagent-pr-contract: machine-checked at merge; replace each "
        'tests:["TODO"] with the pytest nodeids that prove that AC -->\n'
        "<details>\n"
        "<summary>codeagent-pr-contract v1</summary>\n\n"
        "```json\n"
        f"{payload}\n"
        "```\n"
        "</details>"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Emit a codeagent-pr-contract skeleton.")
    ap.add_argument("--issue-body-file", help="file with the issue body (default: stdin)")
    ap.add_argument("--issue", type=int, help="override implements_issue")
    args = ap.parse_args(argv)
    body = (
        open(args.issue_body_file, encoding="utf-8").read()
        if args.issue_body_file else sys.stdin.read()
    )
    print(render_pr_section(build_pr_contract_skeleton(body, args.issue)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
