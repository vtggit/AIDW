# `ca_gate` — CodeAgent contract merge-gate

This directory holds the self-contained tooling for the CodeAgent **contract
merge-gate**: a PR that implements a deliberated issue must map every active
acceptance criterion (`AC-N`) to a passing test. Pure stdlib + `pytest` — no
dependency on the CodeAgent service.

## Files

| file | purpose |
|---|---|
| `contract_lib.py` | **vendored** from `vtggit/CodeAgent` `src/orchestration/contract_lib.py`. The AC-text hash + the `raw_decode` contract extractor. Do not edit by hand — keep it byte-identical to the source so hashes reproduce. |
| `new_pr_contract.py` | offline generator: turn an issue's `codeagent-contract` into a `codeagent-pr-contract` skeleton (one `proof_map` entry per active AC, `ac_text_hash` filled, `tests:["TODO"]`). |
| `list_proof_nodeids.py` | prints the proving-test nodeids from a PR's `codeagent-pr-contract`, so the gate runs only those tests rather than the whole suite. |
| `check_pr_contract.py` | the checker: resolves the PR contract against the linked issue's `codeagent-contract` and a junit test report, and produces a per-AC verdict. |
| `revalidate.py` | re-checks the issue-side invariants (governance, decision pin, AC text hashes) for every open contract PR and posts a `codeagent-contract-revalidate` check-run on its head commit. |

Unit tests for this tooling live in `tests/ca_gate/`.

## Author workflow

```bash
# from an issue body on disk…
python scripts/ca_gate/new_pr_contract.py --issue-body-file issue.md
# …or straight from GitHub
gh issue view 128 --json body -q .body | python scripts/ca_gate/new_pr_contract.py
```

Paste the printed `## CodeAgent PR Contract` section into your PR description and
replace each `tests: ["TODO"]` with the test nodeid(s) that prove that AC: pytest
nodeids relative to `backend/`, or Playwright specs under `app/tests/`.

## What the gate checks

`check_pr_contract.py` passes a PR only when all of these hold:

- A PR with no contract and no `Implements`/`Closes` link to a contracted issue is
  not gated. A PR that links a contracted issue but omits the PR contract fails.
- Every linked issue can be fetched; a failed fetch fails the check.
- The issue's contract has `may_proceed == true` and no blockers.
- The PR's `decision_id` equals the issue's current decision.
- Every active AC has a `proven` proof-map entry whose `ac_text_hash` matches the
  live AC text and whose mapped tests were all collected and passed.

## Status

Enforcing. Two workflows run this tooling:

- `.github/workflows/codeagent-merge-gate.yml` runs on every pull request (opened,
  pushed, reopened, or description edited), except pull requests that change only
  `docs/**` or Markdown files. It runs the contract's proving tests (pytest
  against PostgreSQL, or the Playwright suite for frontend proofs) and then
  `check_pr_contract.py`. A failing verdict fails the `CodeAgent contract gate`
  check.
- `.github/workflows/codeagent-gate-revalidate.yml` runs `revalidate.py` daily and
  on manual dispatch, so a governance or decision change on an issue can turn an
  open PR's check red without a new push.

A failing check blocks a merge only if the repository's branch settings mark it
as required; [docs/branch-protection.md](../../docs/branch-protection.md) explains how to make
the checks required. The contract schema is specified in CodeAgent `docs/contract-schema.md`.
