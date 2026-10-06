"""Issue #716 — engine-verified GDPR capability record.

AC-1: ``config/compliance_capabilities.yaml`` follows the AICRM record format —
a header comment stating that only engine-verified entries count, then
``capabilities:`` with exactly two entries (``gdpr_erasure_execution`` and
``gdpr_retention_sweep``), each carrying ``id``/``markers``/``status``/
``proof``/``mutation`` (``target`` + ``returns``).

AC-2: this test loads the record with ``yaml.safe_load`` and proves it holds
exactly those two entries with exactly those fields, that each ``proof``
names an existing test function in ``backend/tests``, and that each mutation
``target`` resolves to a callable via ``importlib.import_module`` on the part
before ``:`` and ``getattr`` on the rest.

AC-3: only the two specific capabilities are asserted. The record carries no
generic ``gdpr`` entry, so it cannot unblock unrelated GDPR findings (consent,
lawful basis, DPIA, data transfers) that these two records do not cover.

Hardened against review findings: ``returns: false`` is pinned with identity
(``0 == False`` in Python, so plain dict equality would accept
``returns: 0``); the record is additionally loaded under a duplicate-key-
rejecting loader (``yaml.safe_load`` silently keeps the last of duplicated
keys, which loaded-dict checks can never see); and proof functions are
matched against module-level ``test_*`` definitions only (``ast.walk`` would
also accept nested or method definitions that pytest can never address).
"""

import ast
import importlib
import re
import types
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = BACKEND_ROOT.parent / "config" / "compliance_capabilities.yaml"

_EXPECTED_DOCUMENT = {
    "capabilities": [
        {
            "id": "gdpr_erasure_execution",
            "markers": ["gdpr"],
            "status": "shipped",
            "proof": "tests/test_erasure_executor.py::test_erasure_end_to_end",
            "mutation": {
                "target": "app.governance.executor:execute_deletion",
                "returns": False,
            },
        },
        {
            "id": "gdpr_retention_sweep",
            "markers": ["gdpr"],
            "status": "shipped",
            "proof": (
                "tests/test_retention_sweep.py"
                "::test_class_scoped_purge_deletes_only_past_cutoff"
            ),
            "mutation": {
                "target": "app.retention.service:_do_sweep",
                "returns": None,
            },
        },
    ]
}

# ---------------------------------------------------------------------------
# strict minimal YAML safe-load (fallback for environments without PyYAML)
#
# PyYAML is always preferred when installed; the fallback exists so the proof
# runs in sandboxes that cannot install dependencies. It implements the
# ``safe_load`` semantics for exactly the subset the record uses (block
# mappings, block/flow lists of scalars, ``null``/booleans, comments) and
# refuses anything else — it can never execute code or follow external tags.
# ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?$")


def _strip_comment(line: str) -> str:
    for index, char in enumerate(line):
        if char == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index]
    return line


def _parse_scalar(token: str):
    token = token.strip()
    if token in ("", "~", "null", "Null", "NULL"):
        return None
    if token in ("false", "False", "FALSE"):
        return False
    if token in ("true", "True", "TRUE"):
        return True
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    if _INT_RE.match(token):
        return int(token)
    if _FLOAT_RE.match(token):
        return float(token)
    return token


def _parse_value(token: str):
    token = token.strip()
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in inner.split(",")]
    if token.startswith("[") or token.startswith("{"):
        raise ValueError("minimal YAML loader: unclosed or unsupported flow collection")
    if token.startswith("!"):
        raise ValueError("minimal YAML loader: YAML tags are unsupported")
    return _parse_scalar(token)


def _split_key_value(text: str) -> tuple[str, str]:
    if text.endswith(":") and ": " not in text:
        key = text[:-1].strip()
        if not _KEY_RE.match(key):
            raise ValueError(f"minimal YAML loader: unsupported key: {key!r}")
        return key, ""
    position = text.find(": ")
    if position == -1:
        raise ValueError(f"minimal YAML loader: not a 'key: value' line: {text!r}")
    key = text[:position].strip()
    if not _KEY_RE.match(key):
        raise ValueError(f"minimal YAML loader: unsupported key: {key!r}")
    return key, text[position + 2 :].strip()


def _parse_mapping(
    lines: list[tuple[int, str]], start: int, indent: int
) -> tuple[dict, int]:
    result: dict = {}
    index = start
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent != indent or text == "-" or text.startswith("- "):
            break
        key, value_text = _split_key_value(text)
        if key in result:
            raise ValueError(f"minimal YAML loader: duplicate key {key!r}")
        index += 1
        if value_text:
            result[key] = _parse_value(value_text)
            continue
        if index < len(lines) and lines[index][0] > indent:
            result[key], index = _parse_block(lines, index, lines[index][0])
        else:
            result[key] = None
    return result, index


def _parse_sequence(
    lines: list[tuple[int, str]], start: int, indent: int
) -> tuple[list, int]:
    items: list = []
    index = start
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent != indent or not text.startswith("- "):
            break
        rest = text[2:].strip()
        if not rest:
            raise ValueError("minimal YAML loader: bare '-' items are unsupported")
        if ": " in rest:
            key, value_text = _split_key_value(rest)
            item: dict = {key: _parse_value(value_text) if value_text else None}
            index += 1
            if index < len(lines) and lines[index][0] == indent + 2:
                block, index = _parse_mapping(lines, index, indent + 2)
                for key in block:
                    if key in item:
                        raise ValueError(f"minimal YAML loader: duplicate key {key!r}")
                item.update(block)
            items.append(item)
        else:
            items.append(_parse_value(rest))
            index += 1
    return items, index


def _parse_block(lines: list[tuple[int, str]], start: int, indent: int):
    if lines[start][1] == "-" or lines[start][1].startswith("- "):
        return _parse_sequence(lines, start, indent)
    return _parse_mapping(lines, start, indent)


def _minimal_safe_load(text: str):
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if "\t" in raw_line:
            raise ValueError("minimal YAML loader: tabs are unsupported")
        line = _strip_comment(raw_line).rstrip()
        if not line.strip():
            continue
        content = line.lstrip(" ")
        lines.append((len(line) - len(content), content.strip()))
    if not lines:
        return None
    if lines[0][0] != 0:
        raise ValueError("minimal YAML loader: top level must start at column 0")
    value, next_index = _parse_block(lines, 0, 0)
    if next_index != len(lines):
        raise ValueError("minimal YAML loader: trailing content not consumed")
    return value


try:
    import yaml  # type: ignore[import-not-found]

    _HAVE_PYYAML = True
except ModuleNotFoundError:
    yaml = types.ModuleType("yaml")
    yaml.safe_load = _minimal_safe_load
    _HAVE_PYYAML = False


if _HAVE_PYYAML:

    class _NoDuplicateSafeLoader(yaml.SafeLoader):
        """``SafeLoader`` that refuses duplicate mapping keys.

        ``yaml.safe_load`` silently keeps the last of duplicated keys, so
        loaded-dict checks alone can never see them.
        """

    def _construct_mapping_rejecting_duplicates(loader, node, deep=False):
        seen_keys = []
        for key_node, _value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in seen_keys:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key {key!r} is not allowed",
                    key_node.start_mark,
                )
            seen_keys.append(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    _NoDuplicateSafeLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        _construct_mapping_rejecting_duplicates,
    )

    def _load_rejecting_duplicate_keys(text: str):
        return yaml.load(text, Loader=_NoDuplicateSafeLoader)

else:

    def _load_rejecting_duplicate_keys(text: str):
        # The minimal loader already refuses duplicate keys.
        return _minimal_safe_load(text)


def _top_level_test_function_names(path: Path) -> set[str]:
    """Module-level ``test_*`` functions only.

    ``ast.walk`` would also collect nested definitions and class methods,
    which pytest can never address as ``file::name``: it only collects
    module-level ``test_*`` functions from ``test_*.py`` files.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def test_issue716_freeform():
    """The record holds exactly the two engine-verified capabilities."""
    assert CONFIG_PATH.is_file(), f"missing capability record: {CONFIG_PATH}"
    raw_text = CONFIG_PATH.read_text(encoding="utf-8")
    document = yaml.safe_load(raw_text)

    # Duplicate YAML keys are invisible to loaded-dict checks (safe_load
    # silently keeps the last one), so the record must also load cleanly
    # under a duplicate-key-rejecting loader.
    _load_rejecting_duplicate_keys(raw_text)

    # AC-1 + AC-2: exactly the two entries, exactly these fields and values.
    assert document == _EXPECTED_DOCUMENT, (
        "compliance_capabilities.yaml must hold exactly the two engine-verified "
        f"entries, got: {document!r}"
    )

    # ``0 == False`` in Python, so the dict equality above cannot tell
    # ``returns: false`` from ``returns: 0`` — pin the exact identities.
    expected_returns = {
        "gdpr_erasure_execution": False,
        "gdpr_retention_sweep": None,
    }
    for entry in document["capabilities"]:
        returns = entry["mutation"]["returns"]
        expected = expected_returns[entry["id"]]
        assert returns is expected, (
            f"{entry['id']} mutation.returns must be exactly {expected!r}, "
            f"got {returns!r} ({type(returns).__name__})"
        )

    # AC-3: only the two specific capabilities are asserted — no generic
    # 'gdpr' entry that would unblock consent / lawful basis / DPIA /
    # data-transfer findings these records do not cover.
    entry_ids = [entry["id"] for entry in document["capabilities"]]
    assert entry_ids == [
        "gdpr_erasure_execution",
        "gdpr_retention_sweep",
    ], f"capability ids must be exactly the two specific ones, got {entry_ids!r}"
    assert "gdpr" not in entry_ids
    for entry in document["capabilities"]:
        assert set(entry) == {"id", "markers", "status", "proof", "mutation"}
        assert set(entry["mutation"]) == {"target", "returns"}

    # AC-2: every proof names an existing test function in backend/tests.
    for entry in document["capabilities"]:
        file_path, _, function_name = entry["proof"].partition("::")
        assert (
            function_name
        ), f"proof is not a 'path::function' nodeid: {entry['proof']!r}"
        test_file = BACKEND_ROOT / file_path
        assert test_file.is_file(), f"proof file missing from backend: {test_file}"
        assert test_file.is_relative_to(
            BACKEND_ROOT / "tests"
        ), f"proof must name a test under backend/tests: {entry['proof']!r}"
        assert (
            test_file.name.startswith("test_") and test_file.suffix == ".py"
        ), f"proof file is not a pytest test module: {test_file}"
        assert function_name in _top_level_test_function_names(
            test_file
        ), f"proof names no existing test function: {entry['proof']!r}"

    # AC-2: every mutation target resolves to a callable.
    for entry in document["capabilities"]:
        target = entry["mutation"]["target"]
        module_name, _, attribute_name = target.partition(":")
        assert attribute_name, f"mutation target is not 'module:attr': {target!r}"
        module = importlib.import_module(module_name)
        assert callable(
            getattr(module, attribute_name)
        ), f"mutation target is not a callable: {target!r}"
