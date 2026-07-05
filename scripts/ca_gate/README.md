# `ca_gate` — CodeAgent contract merge-gate (scaffolding)

This directory holds the self-contained tooling for the CodeAgent **contract
merge-gate**: a PR that implements a deliberated issue must map every active
acceptance criterion (`AC-N`) to a passing test, and (in a later phase) CI blocks
merge until it does. Pure stdlib + `pytest` — no dependency on the CodeAgent
service.

## Files

| file | purpose |
|---|---|
| `contract_lib.py` | **vendored** from `vtggit/CodeAgent` `src/orchestration/contract_lib.py`. The AC-text hash + the `raw_decode` contract extractor. Do not edit by hand — keep it byte-identical to the source so hashes reproduce. |
| `new_pr_contract.py` | offline generator: turn an issue's `codeagent-contract` into a `codeagent-pr-contract` skeleton (one `proof_map` entry per active AC, `ac_text_hash` filled, `tests:["TODO"]`). |

## Author workflow (today)

```bash
# from an issue body on disk…
python scripts/ca_gate/new_pr_contract.py --issue-body-file issue.md
# …or straight from GitHub
gh issue view 128 --json body -q .body | python scripts/ca_gate/new_pr_contract.py
```

Paste the printed `## CodeAgent PR Contract` section into your PR description and
replace each `tests: ["TODO"]` with the pytest nodeid(s) that prove that AC.

## Status

Phase **4a.1** — scaffolding only. Nothing is enforced yet. The CI workflow that
actually reads this contract, runs the suite, and blocks merge lands in a later
phase (4a.3 report-only → 4a.4 required). See the schema spec in CodeAgent
`docs/contract-schema.md`.
