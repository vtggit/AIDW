"""List the proving-test nodeids from a PR's ``codeagent-pr-contract`` proof-map.

Prints one nodeid per line (deduped, order-preserving; None/``TODO`` filtered) so the
merge-gate can run ONLY the contract's proving tests instead of the whole suite — the
full-suite regression is backend-ci's job. Empty output means the PR has no mapped proving
tests (no PR contract, or every entry is still TODO); the merge-gate then emits an empty
junit and ``check_pr_contract.py`` reports the missing proof as usual.

Pure stdlib + the vendored ``contract_lib`` (same dir). Run from the repo root so Python
puts ``scripts/ca_gate/`` on ``sys.path[0]`` and ``import contract_lib`` resolves.
"""

from __future__ import annotations

import argparse

from contract_lib import PR_SCHEMA, extract_contract_json


def proof_nodeids(pr_body: str) -> list[str]:
    """Union of proving BASE nodeids across the PR contract's proof-map, in first-seen order.

    Mirrors ``check_pr_contract.py``: each ``tests`` entry is either a bare nodeid string
    or a ``{"nodeid": ...}`` dict; ``None`` and the placeholder ``"TODO"`` are dropped. The
    ``[param]`` suffix is stripped to the BASE nodeid so pytest collects EVERY parametrization
    — the gate verifies a base "passes iff some case passed AND none failed", so running only a
    pinned case would miss a broken sibling. Stripping also collapses ``t[a]``/``t[b]`` to one run.
    """
    pr = extract_contract_json(pr_body or "", PR_SCHEMA)
    if not pr:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for entry in pr.get("proof_map") or []:
        for t in entry.get("tests") or []:
            nodeid = t.get("nodeid") if isinstance(t, dict) else t
            if not nodeid or nodeid == "TODO":
                continue
            base = nodeid.split("[", 1)[0]  # base nodeid: run all parametrizations
            if base not in seen:
                seen.add(base)
                out.append(base)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pr-body-file", required=True)
    args = ap.parse_args(argv)
    with open(args.pr_body_file, encoding="utf-8") as fh:
        body = fh.read()
    for nodeid in proof_nodeids(body):
        print(nodeid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
