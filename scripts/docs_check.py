#!/usr/bin/env python3
"""Docs check: a light, dependency-free check of the Markdown files a pull request changes.

The backend CI and the CodeAgent merge gate both ignore Markdown-only changes, so a
docs-only pull request used to get no checks at all and could never pass the "every check
green" merge path. This check gives such a pull request a real check of its own. For each
changed ``.md`` file it reports:

1. a fenced code block that is never closed;
2. a relative link whose target does not exist in the checkout;
3. a private IPv4 address (10/8, 172.16/12, 192.168/16) — internal hosts must not be
   published in docs;
4. a line that assigns a literal value to a password, secret, token or API key, unless the
   value is an obvious placeholder.

Usage:
    python3 scripts/docs_check.py <base-ref>          # the .md files changed since <base-ref>
    python3 scripts/docs_check.py --files A.md B.md    # these files

Exit status 0 when every file is clean, 1 on any finding (one ``path:line: reason`` per line).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_INLINE_CODE_RE = re.compile(r"`+[^`]*`+")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_PRIVATE_IP_RE = re.compile(
    r"(?<![\d.])(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}(?!\.?\d)"
)
# An assignment (NAME=value, as in a shell or .env line) or a quoted JSON/YAML key
# ("password": "value"); prose such as "API key: the X-Api-Key header" is not matched.
_SECRET_RES = (
    re.compile(
        r"(?i)\b[A-Za-z0-9_]*(?:password|passwd|secret|token|api[_-]?key)\s*=\s*[\"']?([^\s\"'`|,;]+)"
    ),
    re.compile(
        r"(?i)[\"'][A-Za-z0-9_]*(?:password|passwd|secret|token|api[_-]?key)[\"']\s*:\s*[\"']([^\"']+)[\"']"
    ),
)
_PLACEHOLDER_RE = re.compile(
    r"(?i)^(?:<.*>|\$\{?.*|\*{3,}.*|x{3,}|\.{3}|change[-_]?me.*|your[-_].*|example.*|"
    r"(?:dev|test|local|demo)[-_].*|"
    r"placeholder.*|redacted.*|none|null|true|false|\(.*\)|\[.*\]|\{.*\})$"
)


def _strip_inline_code(line: str) -> str:
    return _INLINE_CODE_RE.sub("", line)


def _link_target_ok(target: str, md_path: Path) -> bool:
    if _SCHEME_RE.match(target) or target.startswith("#"):
        return True
    path_part = target.split("#", 1)[0].split("?", 1)[0]
    if not path_part:
        return True
    base = REPO_ROOT if path_part.startswith("/") else md_path.parent
    return (base / path_part.lstrip("/")).exists()


def check_file(md_path: Path) -> list[str]:
    """Every finding for one Markdown file, as ``path:line: reason``."""
    try:
        rel = md_path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = md_path
    try:
        lines = md_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{rel}:0: cannot be read as UTF-8 text ({exc.__class__.__name__})"]
    findings: list[str] = []
    fence: str | None = None
    fence_line = 0
    for number, line in enumerate(lines, 1):
        opening = _FENCE_RE.match(line)
        if opening:
            mark = opening.group(1)
            if fence is None:
                fence, fence_line = mark, number
            elif (
                mark[0] == fence[0]
                and len(mark) >= len(fence)
                and not line.strip()[len(mark) :].strip()
            ):
                fence = None
        if fence is None and not opening:
            for target in _LINK_RE.findall(_strip_inline_code(line)):
                if not _link_target_ok(target, md_path):
                    findings.append(
                        f"{rel}:{number}: relative link target does not exist: {target}"
                    )
        for address in _PRIVATE_IP_RE.findall(line):
            findings.append(
                f"{rel}:{number}: private IP address {address} (do not publish internal hosts)"
            )
        for pattern in _SECRET_RES:
            for value in pattern.findall(line):
                if not _PLACEHOLDER_RE.match(value):
                    findings.append(
                        f"{rel}:{number}: a password, secret, token or API key is given a literal value"
                    )
    if fence is not None:
        findings.append(f"{rel}:{fence_line}: fenced code block is never closed")
    return findings


def changed_markdown(base_ref: str) -> list[Path]:
    """The Markdown files added, modified or renamed since ``base_ref`` (merge-base diff)."""
    out = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=AMR",
            f"{base_ref}...HEAD",
            "--",
            "*.md",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / name for name in out.splitlines() if name.strip()]


def main(argv: list[str]) -> int:
    if len(argv) >= 1 and argv[0] == "--files":
        files = [Path(a).resolve() for a in argv[1:]]
    elif len(argv) == 1:
        files = changed_markdown(argv[0])
    else:
        print(__doc__.strip().split("Usage:", 1)[1], file=sys.stderr)
        return 2
    findings = [f for path in files for f in check_file(path)]
    for finding in findings:
        print(finding)
    if findings:
        print(f"docs check: {len(findings)} finding(s) in {len(files)} file(s)")
        return 1
    print(f"docs check: {len(files)} file(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
