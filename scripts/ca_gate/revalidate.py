"""Daily re-validation of open contract PRs (contract-v2 Phase 4a.4).

A governance veto or decision change on an ISSUE happens without any push to the
linked PR, so the on-push merge-gate's last (green) run would still let the PR
merge. This cron re-checks the ISSUE-SIDE invariants (governance may_proceed,
decision pin, active-AC text hashes) for every open PR that carries a
``codeagent-pr-contract`` and posts a ``codeagent-contract-revalidate`` check-run
on the PR's head SHA — flipping it red without a new push. It does NOT re-run the
test suite (the code is unchanged since the last gate run, so the test-side
verdict is unchanged).
"""
import json
import os
import urllib.error
import urllib.request

from contract_lib import ISSUE_SCHEMA, PR_SCHEMA, ac_text_hash, extract_contract_json

REPO = os.environ.get("GITHUB_REPOSITORY", "vtggit/AICRM")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
CHECK_NAME = "codeagent-contract-revalidate"


def _api(method, path, data=None):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        data=(json.dumps(data).encode() if data is not None else None), method=method,
        headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
                 "User-Agent": "ca-revalidate", "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.HTTPError as e:
        return e.read()


def _get(path):
    return json.loads(_api("GET", path) or "null")


def revalidate_issue_side(pr_contract: dict, issue_contract) -> tuple:
    """Re-check only the issue-DEPENDENT invariants (no test run). Returns
    (conclusion, reasons) where conclusion is success | failure | neutral."""
    if issue_contract is None:
        return "neutral", ["linked issue has no codeagent-contract"]
    reasons = []
    gov = issue_contract.get("governance") or {}
    if gov.get("may_proceed") is not True or (gov.get("blockers") or []):
        reasons.append("governance not green (may_proceed=%s, blockers=%d)"
                       % (gov.get("may_proceed"), len(gov.get("blockers") or [])))
    issue_decision = (issue_contract.get("decision") or {}).get("id")
    if pr_contract.get("decision_id") != issue_decision:
        reasons.append("stale decision (PR %s vs issue %s)"
                       % (pr_contract.get("decision_id"), issue_decision))
    pm = {e.get("ac"): e for e in (pr_contract.get("proof_map") or [])}
    for ac in (issue_contract.get("acceptance_criteria") or []):
        if ac.get("status") != "active":
            continue
        e = pm.get(ac["id"])
        if e is None or e.get("kind") != "proven":
            reasons.append("%s: no proven proof-map entry" % ac["id"])
        elif e.get("ac_text_hash") != ac_text_hash(ac.get("text", "")):
            reasons.append("%s: AC text changed since proof was written" % ac["id"])
    return ("success" if not reasons else "failure"), reasons


def main():
    prs = _get("/repos/%s/pulls?state=open&per_page=100" % REPO)
    if not isinstance(prs, list):
        print("could not list PRs"); return
    for pr in prs:
        prc = extract_contract_json(pr.get("body") or "", PR_SCHEMA)
        if prc is None:
            continue
        issue_no = prc.get("implements_issue")
        ic = None
        if issue_no is not None:
            issue = _get("/repos/%s/issues/%d" % (REPO, int(issue_no))) or {}
            ic = extract_contract_json(issue.get("body") or "", ISSUE_SCHEMA)
        conclusion, reasons = revalidate_issue_side(prc, ic)
        title = "Contract re-validation: " + {
            "success": "OK", "failure": "FAILED", "neutral": "skipped"}[conclusion]
        summary = "Issue-side re-check (governance / decision / AC text — no test re-run).\n\n" + (
            "\n".join("- " + r for r in reasons) if reasons else "All issue-side invariants hold.")
        _api("POST", "/repos/%s/check-runs" % REPO, {
            "name": CHECK_NAME, "head_sha": pr["head"]["sha"],
            "status": "completed", "conclusion": conclusion,
            "output": {"title": title, "summary": summary}})
        print("PR #%d -> %s (%d reasons)" % (pr["number"], conclusion, len(reasons)))


if __name__ == "__main__":
    main()
