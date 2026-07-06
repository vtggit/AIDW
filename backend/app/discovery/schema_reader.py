"""Deterministic schema discovery — read a source's structure into normalized datasets/fields.

A SchemaReader is chosen by ``sources.type`` (the connector type). OData is the first reader; DB
(information_schema), JDBC/ODBC (catalog), and SQL-dump (DDL) readers slot in behind the same
interface later, all producing the SAME DiscoveredDataset/DiscoveredField shape — so everything
downstream (persistence, profiling, dashboard suggestion) is connector-agnostic.

Pure + stdlib-only (xml.etree): no network, no DB — the caller fetches the metadata and persists
the result. This keeps the reader exhaustively testable against checked-in AND live fixtures.
"""

from __future__ import annotations

import dataclasses
import xml.etree.ElementTree as ET


@dataclasses.dataclass(frozen=True)
class DiscoveredField:
    name: str
    data_type: str  # source-native type (e.g. OData "Edm.String")
    nullable: bool
    is_key: bool


@dataclasses.dataclass(frozen=True)
class DiscoveredDataset:
    name: str  # the source object name (OData EntitySet)
    object_type: str  # e.g. "EntitySet"
    fields: tuple[DiscoveredField, ...]


class SchemaReader:
    """Turn a source's raw schema document into normalized datasets. One subclass per connector."""

    def read(self, metadata: bytes) -> list[DiscoveredDataset]:
        raise NotImplementedError


def _local(tag: str) -> str:
    """Strip the XML namespace so V2/V3/V4 EDMX (which differ only in their namespace URIs) parse
    with one code path."""
    return tag.rsplit("}", 1)[-1]


def _nullable(prop: ET.Element) -> bool:
    v = prop.get("Nullable")
    if v is None:
        return True  # OData default: a property is nullable unless stated
    return v.strip().lower() == "true"


class ODataSchemaReader(SchemaReader):
    """Parse an OData ``$metadata`` (EDMX) document — namespace-agnostic, works for OData V2/V3/V4.

    EntitySets become datasets; each resolves to its EntityType, whose Properties become fields
    (name, native type, nullable, is_key). NavigationProperties are intentionally skipped (they're
    relationships, not columns)."""

    def read(self, metadata: bytes) -> list[DiscoveredDataset]:
        root = ET.fromstring(metadata)

        # 1) index EntityTypes by BOTH short name and Namespace-qualified name (EntitySets
        #    reference the qualified form, e.g. "NorthwindModel.Customer").
        types: dict[str, dict] = {}
        for schema in (e for e in root.iter() if _local(e.tag) == "Schema"):
            ns = schema.get("Namespace") or ""
            for et in (e for e in schema if _local(e.tag) == "EntityType"):
                name = et.get("Name")
                if not name:
                    continue
                keys: set[str] = set()
                props: list[dict] = []
                for child in et:
                    lt = _local(child.tag)
                    if lt == "Key":
                        keys.update(
                            pr.get("Name")
                            for pr in child
                            if _local(pr.tag) == "PropertyRef" and pr.get("Name")
                        )
                    elif lt == "Property" and child.get("Name"):
                        props.append(
                            {
                                "name": child.get("Name"),
                                "type": child.get("Type") or "",
                                "nullable": _nullable(child),
                            }
                        )
                entry = {"name": name, "props": props, "keys": keys}
                types[name] = entry
                if ns:
                    types[f"{ns}.{name}"] = entry

        # 2) EntitySets -> datasets (resolve the referenced EntityType by qualified or short name)
        out: list[DiscoveredDataset] = []
        seen: set[str] = set()
        for es in (e for e in root.iter() if _local(e.tag) == "EntitySet"):
            es_name = es.get("Name")
            if not es_name or es_name in seen:
                continue
            ref = es.get("EntityType") or ""
            t = types.get(ref) or types.get(ref.rsplit(".", 1)[-1])
            if t is None:
                continue  # unresolved type — skip rather than emit a hollow dataset
            seen.add(es_name)
            fields = tuple(
                DiscoveredField(
                    name=p["name"],
                    data_type=p["type"],
                    nullable=p["nullable"],
                    is_key=p["name"] in t["keys"],
                )
                for p in t["props"]
            )
            out.append(
                DiscoveredDataset(name=es_name, object_type="EntitySet", fields=fields)
            )
        return out


# connector-type registry (sources.type -> reader). Grows as new connectors land.
_READERS: dict[str, SchemaReader] = {"odata": ODataSchemaReader()}


def get_reader(connector_type: str) -> SchemaReader:
    """Return the SchemaReader for a connector type, or raise for an unsupported one (fail closed —
    never silently discover nothing)."""
    reader = _READERS.get((connector_type or "").strip().lower())
    if reader is None:
        raise ValueError(
            f"no schema reader for connector type {connector_type!r} "
            f"(have: {', '.join(sorted(_READERS))})"
        )
    return reader
