"""Issue #830: certifi is pinned to 2026.10.19 in backend/constraints.txt."""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

_PIN_RE = re.compile(r"^\s*(?P<name>[A-Za-z0-9._-]+)\s*==\s*(?P<version>[^\s#]+)")


def _pin(line: str):
    """Return ``(name, version)`` when *line* is an exact pin, else ``None``.

    Matching is case-insensitive on the package name and tolerant of
    whitespace around ``==``, so a differently-cased or padded pin such as
    ``Certifi == 2026.7.22`` cannot slip past the check.
    """
    match = _PIN_RE.match(line)
    if match is None:
        return None
    return match.group("name").lower(), match.group("version")


def test_issue830_freeform():
    lines = (BACKEND / "constraints.txt").read_text(encoding="utf-8").splitlines()

    certifi_pins = [
        (line, parsed)
        for line in lines
        if (parsed := _pin(line)) is not None and parsed[0] == "certifi"
    ]
    assert [version for _, (_, version) in certifi_pins] == [
        "2026.10.19"
    ], f"certifi must be pinned exactly to 2026.10.19, got: {certifi_pins}"
    old_pins = [line for line in lines if _pin(line) == ("certifi", "2026.7.22")]
    assert not old_pins, f"the old certifi==2026.7.22 pin is still present: {old_pins}"

    # Proof: pin matching is case- and whitespace-insensitive, so a
    # differently-cased or padded pin is still recognised as the certifi pin.
    assert _pin("certifi==2026.10.19") == ("certifi", "2026.10.19")
    assert _pin("Certifi == 2026.10.19") == ("certifi", "2026.10.19")
    assert _pin("  CERTIFI==2026.10.19\t") == ("certifi", "2026.10.19")
    # Proof: the old-pin check catches differently-cased and padded variants
    # instead of only the literal lowercase ``certifi==2026.7.22`` line.
    assert _pin("Certifi==2026.7.22") == ("certifi", "2026.7.22")
    assert _pin("certifi == 2026.7.22") == ("certifi", "2026.7.22")
