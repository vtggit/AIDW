"""CodeAgent contract merge-gate checker (contract-v2 Phase 4a.3, report-only).

Resolves a PR's ``codeagent-pr-contract`` against the linked issue's
``codeagent-contract`` and a pytest junitxml run, and produces a per-AC verdict.
The pure ``evaluate()`` core takes plain data (no network, no filesystem) so it is
fully unit-testable; ``main()`` wires the real inputs (resolve+fetch every linked
issue, parse junitxml, read test source for the AST guard).

Verdict rules (from the P4a design synthesis):
  * FAIL-OPEN  : no PR contract AND no Implements/Closes link to ANY contracted
                 issue -> ordinary PRs are not gated.
  * FAIL-CLOSED: a PR links a contracted issue but omits the PR contract
                 ("proof-map required") — closes the strip-to-dodge hole even
                 when other (non-contracted) issues are also linked.
  * GOVERNANCE : the live issue contract must have may_proceed==true & no blockers
                 (a footer with may_proceed!=true, incl. mid-flight "pending",
                 fails closed).
  * DECISION   : pr.decision_id must equal the issue's current decision.id.
  * AC COVERAGE: every status=="active" AC must have a kind=="proven" proof-map
                 entry whose ac_text_hash matches the live AC text and whose
                 mapped pytest nodeids were all collected+passed (every
                 parametrization; not skipped/xfail) and non-trivial.

KNOWN GAP (accepted for report-only; must be addressed before 4a.4 becomes a
required check): the AST assertion-floor only proves the mapped test exists and
asserts SOMETHING — it does not prove the test actually exercises the AC. A
proof-map could point at an unrelated green test. Mitigation for 4a.4: require
each mapped test to be added/modified in the PR diff.

In report-only mode the verdict is computed and rendered but the process exits 0.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import xml.etree.ElementTree as ET

from contract_lib import ISSUE_SCHEMA, PR_SCHEMA, ac_text_hash, extract_contract_json

_LINK_RE = re.compile(r"\b(?:implements|closes|fixes|resolves)\b[:\s]+#(\d+)", re.IGNORECASE)
_ASSERT_HELPER_RE = re.compile(r"(?:^|[._])(assert|check|verify|expect|validate)", re.IGNORECASE)


# ── pure verdict core ──────────────────────────────────────────────────────

class Result:
    def __init__(self):
        self.ok = True
        self.fail_open = False
        self.skipped_reason = None
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.ac_rows: list[dict] = []

    def fail(self, reason: str):
        self.ok = False
        self.failures.append(reason)


def extract_prose_issue_links(pr_body: str) -> set[int]:
    return {int(n) for n in _LINK_RE.findall(pr_body or "")}


def evaluate(pr_body, issue_contract, prose_links, junit, nontrivial,
             any_contracted=None, changed_files=None) -> Result:
    """Pure verdict. ``junit`` = {"passed","present","skipped"[, "failed"]} sets of
    nodeids; ``nontrivial`` = callable(nodeid)->bool; ``issue_contract`` is the
    contract of the issue the PR IMPLEMENTS (or None); ``any_contracted`` is True
    iff ANY issue linked by the PR is contracted (defaults to issue_contract is
    not None for the single-issue case)."""
    r = Result()
    pr = extract_contract_json(pr_body or "", PR_SCHEMA)
    if any_contracted is None:
        any_contracted = issue_contract is not None

    # 1. fail-open / fail-closed anchor
    if pr is None:
        if any_contracted:
            r.fail("PR links a contracted issue but has no codeagent-pr-contract "
                   "(proof-map required)")
            return r
        r.fail_open = True
        r.skipped_reason = "no PR contract and no link to a contracted issue"
        return r

    # 2. the implemented issue must be contracted
    if issue_contract is None:
        r.fail_open = True
        r.skipped_reason = "linked issue has no codeagent-contract"
        return r

    # 3. implements link cross-check (prose vs json)
    impl = pr.get("implements_issue")
    if prose_links and impl is not None and impl not in prose_links:
        r.fail("PR contract implements_issue=%s does not match the Implements/Closes "
               "link(s) %s" % (impl, sorted(prose_links)))

    # 4. governance (live)
    gov = issue_contract.get("governance") or {}
    if gov.get("may_proceed") is not True or (gov.get("blockers") or []):
        r.fail("governance not green (may_proceed=%s, resolution_state=%s, blockers=%d)" % (
            gov.get("may_proceed"), gov.get("resolution_state"), len(gov.get("blockers") or [])))

    # 5. decision pin
    issue_decision = (issue_contract.get("decision") or {}).get("id")
    if pr.get("decision_id") != issue_decision:
        r.fail("stale decision: PR pinned %s but issue is now %s — re-deliberate"
               % (pr.get("decision_id"), issue_decision))

    # 6. AC coverage (strict: every active AC proven)
    by_id = {a["id"]: a for a in (issue_contract.get("acceptance_criteria") or [])}
    pm: dict = {}
    for e in (pr.get("proof_map") or []):
        acid = e.get("ac")
        if acid in pm:
            r.warnings.append("proof-map has duplicate entries for %s; using last" % acid)
        pm[acid] = e

    passed, present, skipped = junit["passed"], junit["present"], junit["skipped"]
    active = [a for a in by_id.values() if a.get("status") == "active"]
    for ac in sorted(active, key=lambda a: a["id"]):
        acid = ac["id"]
        row = {"ac": acid, "status": "?", "tests": "", "result": "FAIL", "reason": ""}
        entry = pm.get(acid)
        if entry is None or entry.get("kind") != "proven":
            row["reason"] = "no proven proof-map entry"
            r.fail("%s: %s" % (acid, row["reason"])); r.ac_rows.append(row); continue
        nodeids = [t.get("nodeid") if isinstance(t, dict) else t for t in (entry.get("tests") or [])]
        nodeids = [n for n in nodeids if n and n != "TODO"]
        row["tests"] = ", ".join(nodeids) or "(none)"
        if entry.get("ac_text_hash") != ac_text_hash(ac.get("text", "")):
            row["reason"] = "ac_text_hash stale — AC text changed since proof was written"
            r.fail("%s: %s" % (acid, row["reason"])); r.ac_rows.append(row); continue
        if not nodeids:
            row["reason"] = "no tests mapped (still TODO)"
            r.fail("%s: %s" % (acid, row["reason"])); r.ac_rows.append(row); continue
        bad = []
        for n in nodeids:
            nb = n.split("[")[0]           # match by base nodeid (every parametrization)
            if nb not in present:
                bad.append("%s not collected" % n)
            elif nb in skipped or nb not in passed:
                bad.append("%s did not pass" % n)
            elif not nontrivial(n):
                bad.append("%s is trivial (no real assertion)" % n)
            elif changed_files is not None and nb.split("::")[0] not in changed_files:
                bad.append("%s not added/modified in this PR (an AC must be proven "
                           "by a test in the diff)" % n)
        if bad:
            row["reason"] = "; ".join(bad)
            r.fail("%s: %s" % (acid, row["reason"])); r.ac_rows.append(row); continue
        row["result"], row["status"] = "OK", "proven"
        r.ac_rows.append(row)

    for acid in pm:
        if acid not in by_id:
            r.warnings.append("proof-map references unknown AC %s" % acid)
        elif by_id[acid].get("status") == "retired":
            r.warnings.append("proof-map references retired AC %s (ignored)" % acid)
    return r


# ── real-input helpers ─────────────────────────────────────────────────────

def parse_junit(path: str) -> dict:
    """Collect pass/fail/skip per nodeid. Parametrized cases collapse to a base
    nodeid; a base counts as PASSED only if some case passed AND no case failed."""
    present, has_pass, has_fail, has_skip = set(), set(), set(), set()
    if not path or not os.path.exists(path):
        return {"passed": set(), "present": set(), "skipped": set(), "failed": set()}
    tree = ET.parse(path)
    for tc in tree.iter("testcase"):
        nodeid = _nodeid_from(tc.get("file"), tc.get("classname", ""), tc.get("name", ""))
        present.add(nodeid)
        if any(c.tag in ("failure", "error") for c in tc):
            has_fail.add(nodeid)
        elif any(c.tag == "skipped" for c in tc):
            has_skip.add(nodeid)
        else:
            has_pass.add(nodeid)
    failed = set(has_fail)
    passed = {n for n in has_pass if n not in has_fail}
    skipped = {n for n in present if n in has_skip and n not in has_pass and n not in has_fail}
    return {"passed": passed, "present": present, "skipped": skipped, "failed": failed}


def _nodeid_from(file: str | None, classname: str, name: str) -> str:
    """Build a pytest nodeid, preferring the junit ``file`` attribute (robust)
    and detecting a test class as a trailing CapWords classname segment that is
    not the module stem."""
    base = name.split("[")[0]
    if file:
        stem = os.path.splitext(os.path.basename(file))[0]
        parts = classname.split(".") if classname else []
        klass = parts[-1] if (parts and parts[-1] != stem and parts[-1][:1].isupper()) else None
        return file + "::" + (klass + "::" + base if klass else base)
    if not classname:
        return base
    parts = classname.split(".")
    if parts and parts[-1][:1].isupper():
        return "/".join(parts[:-1]) + ".py::" + parts[-1] + "::" + base
    return "/".join(parts) + ".py::" + base


def ast_test_is_nontrivial(repo_root: str, nodeid: str) -> bool:
    """Shallow AST assertion-floor: a real assert / pytest.raises|warns / an
    assert-helper call. Lenient (report-only) — unparseable/not-found => True so
    we don't false-fail; tuned before enforcing."""
    path = nodeid.split("::", 1)[0]
    funcname = nodeid.split("::")[-1].split("[")[0]
    try:
        tree = ast.parse(open(os.path.join(repo_root, path), encoding="utf-8").read())
    except (OSError, SyntaxError):
        return True
    target = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
            target = node; break
    if target is None:
        return True
    for node in ast.walk(target):
        if isinstance(node, ast.Assert):
            t = node.test
            if not (isinstance(t, ast.Constant) and bool(t.value)) and not (
                    isinstance(t, ast.Name) and t.id == "True"):
                return True
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and _name_of(call.func) in (
                        "pytest.raises", "pytest.warns", "raises", "warns"):
                    return True
        if isinstance(node, ast.Call) and _ASSERT_HELPER_RE.search(_name_of(node.func)):
            return True
    return False


def _name_of(node) -> str:
    if isinstance(node, ast.Attribute):
        return _name_of(node.value) + "." + node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def fetch_issue_body(repo: str, number: int) -> str | None:
    import json
    import urllib.request
    tok = os.environ.get("GITHUB_TOKEN", "")
    req = urllib.request.Request(
        "https://api.github.com/repos/%s/issues/%d" % (repo, number),
        headers={"Authorization": "Bearer " + tok, "User-Agent": "ca-gate",
                 "Accept": "application/vnd.github+json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30)).get("body") or ""
    except Exception:
        return None


def render_summary(r: Result) -> str:
    lines = ["## CodeAgent merge-gate"]
    if r.fail_open:
        lines.append("✅ **Skipped (fail-open):** %s" % r.skipped_reason)
        return "\n".join(lines)
    lines.append("**Result:** %s" % ("✅ PASS" if r.ok else "❌ FAIL"))
    if r.ac_rows:
        lines += ["", "| AC | result | tests | reason |", "|----|----|----|----|"]
        for row in r.ac_rows:
            lines.append("| %s | %s | %s | %s |" % (
                row["ac"], row["result"], row["tests"] or "—", row["reason"] or "—"))
    for f in r.failures:
        if not any(f.endswith(row["reason"]) for row in r.ac_rows if row["reason"]):
            lines.append("- ❌ %s" % f)
    for w in r.warnings:
        lines.append("- ⚠️ %s" % w)
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CodeAgent contract merge-gate checker.")
    ap.add_argument("--pr-body-file", required=True)
    ap.add_argument("--junit", required=True)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "vtggit/AICRM"))
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--report-only", action="store_true",
                    help="compute + render the verdict but always exit 0")
    ap.add_argument("--changed-files-file",
                    help="file of PR changed paths (gh pr diff --name-only); when "
                         "given, every mapped test must live in a changed file")
    args = ap.parse_args(argv)

    pr_body = open(args.pr_body_file, encoding="utf-8").read()
    prose_links = extract_prose_issue_links(pr_body)
    pr = extract_contract_json(pr_body, PR_SCHEMA)

    # resolve EVERY candidate linked issue so a contracted issue can't be hidden
    # behind a lower-numbered non-contracted link.
    candidates = set(prose_links)
    if pr and pr.get("implements_issue") is not None:
        candidates.add(int(pr["implements_issue"]))
    contracts = {n: extract_contract_json(fetch_issue_body(args.repo, int(n)) or "", ISSUE_SCHEMA)
                 for n in candidates}
    any_contracted = any(c is not None for c in contracts.values())
    target = contracts.get(int(pr["implements_issue"])) if (pr and pr.get("implements_issue") is not None) else None

    changed = None
    if args.changed_files_file and os.path.exists(args.changed_files_file):
        prefix = args.repo_root.rstrip("/") + "/" if args.repo_root not in (".", "") else ""
        raw = [ln.strip() for ln in open(args.changed_files_file, encoding="utf-8") if ln.strip()]
        changed = {(p[len(prefix):] if prefix and p.startswith(prefix) else p) for p in raw}

    junit = parse_junit(args.junit)
    # junit nodeids are relative to pytest's rootdir. When the repo has a
    # root-level pyproject.toml, rootdir is the REPO ROOT, so a backend test
    # collects as "backend/tests/x.py::t". The proof-map and changed-files are
    # repo_root-relative ("tests/x.py::t"), so strip the SAME --repo-root prefix
    # from junit nodeids to compare apples-to-apples (otherwise every mapped
    # test reads as "not collected").
    _prefix = args.repo_root.rstrip("/") + "/" if args.repo_root not in (".", "") else ""
    if _prefix:
        junit = {k: {(n[len(_prefix):] if n.startswith(_prefix) else n) for n in v}
                 for k, v in junit.items()}

    r = evaluate(pr_body, target, prose_links, junit,
                 lambda n: ast_test_is_nontrivial(args.repo_root, n),
                 any_contracted=any_contracted, changed_files=changed)

    summary = render_summary(r)
    print(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(summary + "\n")

    if args.report_only:
        if not r.ok:
            print("\n[report-only] would FAIL — not blocking yet.")
        return 0
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
