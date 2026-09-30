"""#645: the contract gate fails closed when a linked issue cannot be fetched, and keeps its
fail-open skip for an issue that was fetched and simply has no contract."""

import os
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "ca_gate")
)

import check_pr_contract as cpc  # noqa: E402

PR_BODY = "Closes #7\n\nAn ordinary pull request with no codeagent-pr-contract block.\n"


def _run(tmp_path, capsys, extra=()):
    body = tmp_path / "pr_body.md"
    body.write_text(PR_BODY, encoding="utf-8")
    code = cpc.main(["--pr-body-file", str(body), "--junit", str(tmp_path / "none.xml"),
                     "--repo", "owner/repo", *extra])
    return code, capsys.readouterr().out


def test_fetch_error_fails_the_check(tmp_path, capsys, monkeypatch):
    def boom(repo, number):
        raise cpc.IssueFetchError("issue #%d: URLError: timed out" % number)

    monkeypatch.setattr(cpc, "fetch_issue_body", boom)
    code, out = _run(tmp_path, capsys)
    assert code == 1
    assert "could not fetch the linked issue(s)" in out and "issue #7" in out
    assert "Skipped (fail-open)" not in out


def test_fetch_error_is_reported_but_not_blocking_in_report_only(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cpc, "fetch_issue_body",
                        lambda repo, n: (_ for _ in ()).throw(cpc.IssueFetchError("issue #7: x")))
    code, out = _run(tmp_path, capsys, extra=("--report-only",))
    assert code == 0 and "would FAIL" in out


def test_fetched_issue_without_contract_keeps_the_fail_open_skip(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cpc, "fetch_issue_body", lambda repo, n: "A plain issue body, no contract.")
    code, out = _run(tmp_path, capsys)
    assert code == 0
    assert "Skipped (fail-open)" in out


@pytest.mark.parametrize("exc", [
    urllib.error.URLError("timed out"),
    urllib.error.HTTPError("https://api.github.com/x", 502, "Bad Gateway", {}, None),
    TimeoutError("read timed out"),
])
def test_fetch_issue_body_raises_on_any_failure(monkeypatch, exc):
    def fail(*_a, **_k):
        raise exc

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(cpc.IssueFetchError, match=r"issue #7"):
        cpc.fetch_issue_body("owner/repo", 7)
