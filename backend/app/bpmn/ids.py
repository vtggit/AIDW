"""BPMN identifier generation and validation utilities."""

import re


class IdCollisionError(Exception):
    """Raised when two distinct source keys resolve to the same element id."""


def slug(key: str) -> str:
    """Produce an XML NCName-safe slug from *key*.

    Every character outside ``[A-Za-z0-9_-]`` is replaced by a single underscore.
    If the result starts with a digit (or is empty), a leading underscore is prepended.
    """
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", key)
    if not sanitized or not (sanitized[0].isalpha() or sanitized[0] == "_"):
        sanitized = "_" + sanitized
    return sanitized


def element_id(prefix: str, key: str) -> str:
    """Compose a prefixed element id from *prefix* and *key*."""
    return f"{prefix}_{slug(key)}"


def assert_unique(pairs):
    """Validate that all ids in *pairs* are unique across distinct source keys.

    Args:
        pairs: Iterable of ``(source_key, id)`` tuples.

    Raises:
        IdCollisionError: If two different ``source_key`` values map to the same ``id``.
    """
    seen = {}
    for source_key, elem_id in pairs:
        if elem_id in seen and seen[elem_id] != source_key:
            raise IdCollisionError(
                f"Duplicate id {elem_id!r} from keys {seen[elem_id]!r} and {source_key!r}"
            )
        seen[elem_id] = source_key
