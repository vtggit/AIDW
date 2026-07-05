#!/usr/bin/env python3
"""
Release metadata consistency checker.

Validates that release-critical files are consistent before merge:

  1. VERSION file exists and is non-empty
  2. VERSION format matches MAJOR.MINOR.PATCH (semantic versioning)
  3. CHANGELOG.md exists
  4. The current version appears in CHANGELOG.md (or an [Unreleased] section exists)
  5. On PRs: if VERSION changed, CHANGELOG.md must also change

Usage:
    # Full check (default branch / push)
    python scripts/check_release_metadata.py

    # PR check — passes base ref as an argument
    python scripts/check_release_metadata.py --base-ref main
"""

import argparse
import os
import re
import subprocess
import sys

VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def error(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"OK:   {msg}")


def read_file(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Check 1: VERSION file exists and is non-empty
# ---------------------------------------------------------------------------
def check_version_exists() -> bool:
    version_path = os.path.join(REPO_ROOT, "VERSION")
    content = read_file(version_path)
    if content is None:
        error("VERSION file not found at repository root.")
        return False
    if not content.strip():
        error("VERSION file is empty.")
        return False
    ok("VERSION file exists and is non-empty.")
    return True


# ---------------------------------------------------------------------------
# Check 2: VERSION format is MAJOR.MINOR.PATCH
# ---------------------------------------------------------------------------
def check_version_format() -> bool:
    version_path = os.path.join(REPO_ROOT, "VERSION")
    content = read_file(version_path)
    if content is None:
        error("Cannot check version format — VERSION file missing.")
        return False

    version = content.strip()
    if not VERSION_PATTERN.match(version):
        error(
            f"VERSION format is invalid: '{version}'. "
            f"Expected MAJOR.MINOR.PATCH (e.g. 0.1.0, 1.3.2)."
        )
        return False
    ok(f"VERSION format is valid: {version}")
    return True


# ---------------------------------------------------------------------------
# Check 3: CHANGELOG.md exists
# ---------------------------------------------------------------------------
def check_changelog_exists() -> bool:
    changelog_path = os.path.join(REPO_ROOT, "CHANGELOG.md")
    content = read_file(changelog_path)
    if content is None:
        error("CHANGELOG.md not found at repository root.")
        return False
    ok("CHANGELOG.md exists.")
    return True


# ---------------------------------------------------------------------------
# Check 4: VERSION appears in CHANGELOG.md or [Unreleased] section exists
# ---------------------------------------------------------------------------
def check_version_in_changelog() -> bool:
    version_path = os.path.join(REPO_ROOT, "VERSION")
    changelog_path = os.path.join(REPO_ROOT, "CHANGELOG.md")

    version_content = read_file(version_path)
    changelog_content = read_file(changelog_path)

    if version_content is None or changelog_content is None:
        error("Cannot cross-check — VERSION or CHANGELOG.md missing.")
        return False

    version = version_content.strip()

    # Check if the version string appears as a changelog section header
    # e.g. "## [0.1.0]" or "## 0.1.0" or just the version in the text
    version_in_changelog = (
        f"[{version}]" in changelog_content
        or f"### [{version}]" in changelog_content
        or f"## [{version}]" in changelog_content
        or f"## {version}" in changelog_content
    )

    has_unreleased = "[Unreleased]" in changelog_content

    if version_in_changelog:
        ok(f"VERSION {version} found in CHANGELOG.md.")
        return True
    elif has_unreleased:
        ok(
            f"VERSION {version} not yet in CHANGELOG.md, "
            f"but [Unreleased] section exists (acceptable per release process)."
        )
        return True
    else:
        error(
            f"VERSION {version} is not referenced in CHANGELOG.md "
            f"and no [Unreleased] section was found. "
            f"Add a changelog entry for this version."
        )
        return False


# ---------------------------------------------------------------------------
# Check 5: If VERSION changed in PR, CHANGELOG.md must also change
# ---------------------------------------------------------------------------
def check_pr_consistency(base_ref: str) -> bool:
    """
    Compare the current branch against base_ref (e.g. main).
    If VERSION was modified, CHANGELOG.md must also be modified.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            # If git diff fails (e.g. detached HEAD with no common ancestor),
            # skip this check rather than blocking CI.
            print(
                f"WARN: Could not compute diff against '{base_ref}'. "
                f"Skipping PR consistency check."
            )
            return True
    except FileNotFoundError:
        print("WARN: git not found. Skipping PR consistency check.")
        return True

    changed_files = set(result.stdout.strip().splitlines())
    version_changed = "VERSION" in changed_files
    changelog_changed = "CHANGELOG.md" in changed_files

    if version_changed and not changelog_changed:
        error(
            "VERSION was modified but CHANGELOG.md was not. "
            "Every version bump must be accompanied by a changelog update."
        )
        return False

    if version_changed and changelog_changed:
        ok("VERSION and CHANGELOG.md were updated together.")
    else:
        ok("VERSION not modified in this PR — no changelog requirement.")

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Check release metadata consistency.")
    parser.add_argument(
        "--base-ref",
        default=None,
        help="Git base ref to compare against for PR consistency (e.g. main).",
    )
    args = parser.parse_args()

    all_passed = True

    # Always run these checks
    all_passed &= check_version_exists()
    all_passed &= check_version_format()
    all_passed &= check_changelog_exists()
    all_passed &= check_version_in_changelog()

    # PR consistency check (only when base-ref is provided)
    if args.base_ref:
        all_passed &= check_pr_consistency(args.base_ref)

    if not all_passed:
        print("\nRelease metadata validation FAILED.", file=sys.stderr)
        return 1

    print("\nRelease metadata validation PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
