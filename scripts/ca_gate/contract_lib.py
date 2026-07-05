"""Shared contract helpers — VENDORED, do not edit by hand.

Source of truth: vtggit/CodeAgent ``src/orchestration/contract_lib.py``. This is
a byte-for-byte copy of the three functions so the AICRM merge-gate never depends
on the CodeAgent service being importable. The ``normalize_ac_text`` here MUST
stay identical to the source, or proof hashes won't reproduce across repos.

Pure stdlib (re, json, hashlib). Keep it that way.
"""
from __future__ import annotations

import hashlib
import json
import re

ISSUE_SCHEMA = "codeagent-contract"
PR_SCHEMA = "codeagent-pr-contract"


def normalize_ac_text(text: str) -> str:
    """strip + collapse-all-whitespace + casefold (no punctuation stripping)."""
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def ac_text_hash(text: str) -> str:
    """Stable, cross-repo ``sha256:<hex>`` over the normalized AC text."""
    digest = hashlib.sha256(normalize_ac_text(text).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def extract_contract_json(text: str, schemas=(ISSUE_SCHEMA, PR_SCHEMA)) -> dict | None:
    """First fenced ```json block whose ``schema`` is in *schemas*, else None.

    raw_decode anchored at the first ``{`` after each json fence so a brace or
    code-fence inside a string value can't truncate the capture.
    """
    if isinstance(schemas, str):
        schemas = (schemas,)
    decoder = json.JSONDecoder()
    body = text or ""
    for m in re.finditer(r"```json", body):
        start = body.find("{", m.end())
        if start == -1:
            continue
        try:
            obj, _ = decoder.raw_decode(body, start)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict) and obj.get("schema") in schemas:
            return obj
    return None
