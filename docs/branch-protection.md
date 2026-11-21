# Making the CodeAgent contract gate a required check

The merge gate (`.github/workflows/codeagent-merge-gate.yml`) runs **enforcing**: a failing
verdict fails the job, so the check turns red. A red check blocks a merge in GitHub only
when the check is marked **required** in branch protection.

## Current state (2026-11-02)

`main` has no branch protection rule today, so GitHub itself does not block a merge on a
red gate. The gate is enforced by how merges are made: the engine's auto-merge and the
maintainers' pinned merges both require every named check, `CodeAgent contract gate`
included, to have succeeded on the exact commit being merged. Marking the check required
in GitHub, as described below, is a separate switch for the repository owner.

The named checks are the five Backend CI jobs and the contract gate. A pull request that
changes only Markdown or `docs/` gets none of them; it gets the `Docs check` instead
(`.github/workflows/docs-check.yml`).

## The checks

- **`CodeAgent contract gate`**: the per-push gate job. It first runs the gate scripts' own
  tests (`tests/ca_gate/`); a failure there fails the job, because a broken gate's verdict
  means nothing.
- **`codeagent-contract-revalidate`**: the daily re-validation check
  (`.github/workflows/codeagent-gate-revalidate.yml`), so a governance veto raised after a
  pull request's last push still shows on it once the schedule re-runs.

## Make the checks required

Read this first: a required check that never reports leaves a pull request waiting for good.
Both checks above are conditional. `CodeAgent contract gate` does not run on a pull request
that changes only Markdown or `docs/`, and `codeagent-contract-revalidate` is posted only on
open pull requests that carry a contract. Requiring them as they stand would block every
docs-only pull request and every pull request without a contract, so those paths need a
solution before this switch is turned on.

GitHub, repository **Settings**, **Branches**, **Branch protection rules**, `main`,
*Require status checks to pass before merging*, then add the two checks above.

Or through the API, with the repository owner's token. `main` has no rule yet, so this
creates one; the narrower `.../protection/required_status_checks` endpoint answers 404
("Branch not protected") until a rule exists:

```bash
gh api -X PUT repos/vtggit/AIDW/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": {
    "strict": false,
    "checks": [
      {"context": "CodeAgent contract gate"},
      {"context": "codeagent-contract-revalidate"}
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null
}
JSON
```

## Author workflow

For a pull request that implements a CodeAgent-deliberated issue:

```bash
# generate the PR-contract skeleton from the issue contract
gh issue view <N> --json body -q .body | python scripts/ca_gate/new_pr_contract.py
```

Paste the printed `## CodeAgent PR Contract` section into the pull request description,
then replace each `tests: ["TODO"]` with the test ids that prove that criterion. For
every **active** `AC-N` the gate requires:

- a `kind: "proven"` proof-map entry whose `ac_text_hash` matches the live criterion text;
- every mapped test **collected and passing** (all parametrizations, not skipped),
  **non-trivial** (a real assertion), and **added or modified in this pull request's diff**;
- the issue's `governance.may_proceed == true`, and the pinned `decision_id` matching the
  issue's current decision;
- every linked issue fetched. A linked issue that cannot be fetched fails the check.

## Known limitation

The assertion check proves that a mapped test exists and asserts *something*. Combined with
the changed-files binding (the test must be in the diff) it is hard to satisfy with an
unrelated existing test, but it does not prove the test exercises *that* criterion. A
refactor that re-proves a criterion with an unchanged test fails the changed-files binding:
touch the test again, or split the refactor.
