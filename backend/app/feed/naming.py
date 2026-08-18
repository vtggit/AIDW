"""OData naming helpers for the feed surface.

Pure, dependency-free helpers that turn free-form dataset names and
source-native data types into the canonical OData v4 identifiers and
``Edm.*`` type names the feed exposes. No database, no I/O — the feed
service calls these to build a stable, collision-free entity-set name
per dataset and to normalise a field's ``data_type`` string (such as the
``Edm.String`` values produced by the discovery schema reader) into its
canonical OData v4 spelling.
"""

from __future__ import annotations

import re

# Maximum length of an OData identifier produced by ``odata_identifier``.
_MAX_IDENTIFIER_LENGTH = 128

# Characters allowed verbatim in an OData identifier; everything else is
# replaced with an underscore.
_ALLOWED_CHARS = re.compile(r"[^A-Za-z0-9_]")

# OData v4 primitive types, keyed by their lower-cased canonical spelling.
# A name that matches one of these (case-insensitively, with the ``Edm.``
# prefix intact) passes through as its canonical spelling.
_V4_PRIMITIVES: dict[str, str] = {
    "edm.string": "Edm.String",
    "edm.boolean": "Edm.Boolean",
    "edm.byte": "Edm.Byte",
    "edm.sbyte": "Edm.SByte",
    "edm.int16": "Edm.Int16",
    "edm.int32": "Edm.Int32",
    "edm.int64": "Edm.Int64",
    "edm.decimal": "Edm.Decimal",
    "edm.double": "Edm.Double",
    "edm.single": "Edm.Single",
    "edm.guid": "Edm.Guid",
    "edm.date": "Edm.Date",
    "edm.datetimeoffset": "Edm.DateTimeOffset",
    "edm.timeofday": "Edm.TimeOfDay",
    "edm.duration": "Edm.Duration",
    "edm.binary": "Edm.Binary",
}

# Legacy OData v2/v3 primitive names mapped to their OData v4 spelling.
_LEGACY_V2_V3: dict[str, str] = {
    "edm.datetime": "Edm.DateTimeOffset",
    "edm.time": "Edm.TimeOfDay",
    "edm.float": "Edm.Single",
}

# SQL-style type names mapped to their OData v4 spelling.
_SQL_TYPES: dict[str, str] = {
    "int": "Edm.Int32",
    "integer": "Edm.Int32",
    "smallint": "Edm.Int32",
    "bigint": "Edm.Int64",
    "bool": "Edm.Boolean",
    "boolean": "Edm.Boolean",
    "numeric": "Edm.Decimal",
    "decimal": "Edm.Decimal",
    "money": "Edm.Decimal",
    "real": "Edm.Double",
    "float": "Edm.Double",
    "double": "Edm.Double",
    "date": "Edm.Date",
    "uuid": "Edm.Guid",
}


def odata_identifier(name: str) -> str:
    """Return an OData-safe identifier for ``name``.

    Every character other than ``[A-Za-z0-9_]`` is replaced with an
    underscore. If the result is empty or starts with a digit, a leading
    underscore is prepended. The result is then capped at 128 characters.
    The steps are applied in that order, so the returned value never
    exceeds 128 characters.
    """
    sanitized = _ALLOWED_CHARS.sub("_", name)
    if not sanitized or sanitized[0].isdigit():
        sanitized = "_" + sanitized
    return sanitized[:_MAX_IDENTIFIER_LENGTH]


def entity_set_names(datasets: list[dict]) -> dict[str, str]:
    """Map each dataset to a unique OData entity-set name.

    Returns ``{set name: dataset id}`` with exactly one entry per dataset.
    Each input dict carries ``id``, ``name`` and ``created_at``. The set
    name is ``odata_identifier(dataset name)``. Datasets are visited in
    ascending ``(created_at, id)`` order regardless of their position in
    the input, so the earliest-created dataset keeps the bare name and any
    later dataset that collides is suffixed ``_2``, ``_3``, ... The
    mapping is therefore stable across calls.
    """
    ordered = sorted(datasets, key=lambda d: (d["created_at"], d["id"]))
    result: dict[str, str] = {}
    used: set[str] = set()
    for dataset in ordered:
        base = odata_identifier(dataset["name"])
        candidate = base
        suffix = 1
        while candidate in used:
            suffix += 1
            candidate = f"{base}_{suffix}"
        used.add(candidate)
        result[candidate] = dataset["id"]
    return result


def edm_type_for(data_type: str | None) -> str:
    """Return the canonical OData v4 ``Edm.*`` type for a source-native type.

    Matching is case-insensitive and the ``Edm.`` prefix is part of the
    name (never stripped before matching). An OData v4 primitive passes
    through as its canonical spelling; legacy v2/v3 names and SQL-style
    names are mapped to their v4 equivalent. Anything else — including
    ``None`` and the empty string — maps to ``Edm.String``.
    """
    if data_type is None:
        return "Edm.String"
    key = data_type.strip().lower()
    if not key:
        return "Edm.String"

    if key in _V4_PRIMITIVES:
        return _V4_PRIMITIVES[key]
    if key in _LEGACY_V2_V3:
        return _LEGACY_V2_V3[key]
    if key in _SQL_TYPES:
        return _SQL_TYPES[key]
    if key.startswith("timestamp") or key.startswith("datetime"):
        return "Edm.DateTimeOffset"

    return "Edm.String"
