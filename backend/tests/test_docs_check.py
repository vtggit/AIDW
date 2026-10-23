"""The docs check (scripts/docs_check.py) on small Markdown files.

Markdown-only pull requests get no backend CI or merge-gate run, so this check is the only
check such a pull request gets: each rule must catch its case and pass clean text.
"""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "docs_check.py"
_spec = importlib.util.spec_from_file_location("docs_check", _SCRIPT)
docs_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(docs_check)


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_clean_file_has_no_findings(tmp_path):
    _write(tmp_path, "other.md", "# Other\n")
    path = _write(
        tmp_path,
        "doc.md",
        "# Title\n\nSee [other](other.md#part), [site](https://example.com) and [top](#title).\n"
        "Local only: http://127.0.0.1:8080 and 0.0.0.0.\n\n"
        "```bash\nexport DB_PASSWORD=change-me AUTH_DEV_TOKEN=dev-secret-token KEY=${KEY}\n```\n"
        "The API key: the X-Api-Key header carries it.\n",
    )
    assert docs_check.check_file(path) == []


def test_unclosed_fence_is_reported(tmp_path):
    path = _write(tmp_path, "doc.md", "# T\n\n```python\nprint(1)\n")
    (finding,) = docs_check.check_file(path)
    assert ":3: fenced code block is never closed" in finding


def test_longer_fence_closes_and_inner_fence_does_not(tmp_path):
    path = _write(tmp_path, "doc.md", "````\n```\nnot a close\n```\n````\n")
    assert docs_check.check_file(path) == []


def test_broken_relative_link_is_reported_but_not_inside_code(tmp_path):
    path = _write(
        tmp_path,
        "doc.md",
        "[gone](missing.md)\n`[inline](nope.md)`\n```\n[in code](nope.md)\n```\n",
    )
    (finding,) = docs_check.check_file(path)
    assert ":1: relative link target does not exist: missing.md" in finding


def test_private_ip_is_reported(tmp_path):
    path = _write(
        tmp_path, "doc.md", "a\nThe server is at 10.1.2.3:9443 and 192.168.0.4.\n"
    )
    findings = docs_check.check_file(path)
    assert len(findings) == 2
    assert all(":2: private IP address" in f for f in findings)
    assert _write(
        tmp_path, "ok.md", "172.32.0.1 and 1.10.1.1\n"
    ) and not docs_check.check_file(tmp_path / "ok.md")


def test_literal_secret_is_reported_and_placeholders_are_not(tmp_path):
    path = _write(
        tmp_path,
        "doc.md",
        "DB_PASSWORD=hunter2\n"
        '{"api_key": "abc123def456"}\n'
        "API_KEY_SECRET=<generate-one>\n"
        "GITHUB_TOKEN=${GITHUB_TOKEN}\n",
    )
    findings = docs_check.check_file(path)
    assert [f.split(":")[1] for f in findings] == ["1", "2"]
    assert all("given a literal value" in f for f in findings)


def test_main_exit_codes(tmp_path, capsys):
    good = _write(tmp_path, "good.md", "# Fine\n")
    bad = _write(tmp_path, "bad.md", "```\nopen\n")
    assert docs_check.main(["--files", str(good)]) == 0
    assert "1 file(s) clean" in capsys.readouterr().out
    assert docs_check.main(["--files", str(good), str(bad)]) == 1
    assert "1 finding(s) in 2 file(s)" in capsys.readouterr().out
    assert docs_check.main([]) == 2
