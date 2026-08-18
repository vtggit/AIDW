"""OData v4 feed surface.

Exposes the discovered datasets as an OData v4 service: a service document at
the service root, a CSDL 4.0 EDMX metadata document at ``/$metadata``, and an
entity-set read at ``/{entity_set}`` that renders the ingested payloads for a
dataset as OData v4 entity instances.

This module performs no credential handling of its own — every route depends
on :func:`app.feed.auth.require_feed_credential`, and no Basic / X-Api-Key
parsing happens here.  Naming is delegated to :mod:`app.feed.naming`, and the
database is read only through :func:`app.db.connection.get_cursor`.  Every
response carries the ``OData-Version: 4.0`` header.
"""

import os
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.db.connection import get_cursor
from app.feed.auth import require_feed_credential
from app.feed.naming import edm_type_for, entity_set_names, odata_identifier

router = APIRouter(prefix="/api/feed/v4", tags=["feed-odata"])

_ODATA_VERSION = "4.0"

# System query options the entity-set read understands. Anything else that
# starts with ``$`` is rejected with 501.
_SUPPORTED_QUERY_OPTIONS = {"$top", "$skip", "$count", "$select", "$orderby"}

_NUMERIC_EDM_TYPES = {
    "Edm.Int16",
    "Edm.Int32",
    "Edm.Int64",
    "Edm.Byte",
    "Edm.SByte",
    "Edm.Decimal",
    "Edm.Double",
    "Edm.Single",
}
_DATE_EDM_TYPES = {"Edm.DateTimeOffset", "Edm.Date"}


def _odata_headers() -> dict[str, str]:
    """Headers every feed response must carry."""
    return {"OData-Version": _ODATA_VERSION}


def _odata_error(status: int, message: str) -> JSONResponse:
    """Build the standard OData error response body and headers."""
    return JSONResponse(
        status_code=status,
        content={"error": {"code": str(status), "message": message}},
        headers=_odata_headers(),
    )


def _load_datasets() -> list[dict]:
    """Return the datasets rows the feed exposes, in stable order."""
    with get_cursor() as cur:
        cur.execute("SELECT id, name, created_at FROM datasets ORDER BY id")
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def _load_fields(dataset_id: str) -> list[dict]:
    """Return the discovered fields for a single dataset."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT name, data_type FROM discovered_fields "
            "WHERE dataset_id = %s ORDER BY name",
            (dataset_id,),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def _load_payloads(dataset_id: str) -> list[dict]:
    """Return the ingested payloads for a dataset, ordered by business_key."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT business_key, payload FROM ingested_payloads "
            "WHERE dataset_id = %s ORDER BY business_key",
            (dataset_id,),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def _xml_escape(value: str) -> str:
    """Escape a value for safe inclusion in XML text/attribute content."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _page_size() -> int:
    """Return the feed page size, read from the environment at call time."""
    raw = os.environ.get("FEED_PAGE_SIZE")
    if raw is None:
        return 1000
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1000
    return value if value > 0 else 1000


def _parse_int_option(value: str) -> int | None:
    """Parse a non-negative integer query option; ``None`` when invalid."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _build_next_link(
    base_url: str,
    set_name: str,
    skip: int,
    top: int | None,
    count: bool,
    select: str | None = None,
    orderby: str | None = None,
) -> str:
    """Build the ``@odata.nextLink`` for the next page of a set read."""
    parts = [f"{base_url}/api/feed/v4/{set_name}?$skip={skip}"]
    if top is not None:
        parts.append(f"&$top={top}")
    if count:
        parts.append("&$count=true")
    if select is not None:
        parts.append(f"&$select={quote(select, safe=',')}")
    if orderby is not None:
        parts.append(f"&$orderby={quote(orderby, safe=',')}")
    return "".join(parts)


def _advertised_properties(fields: list[dict]) -> dict[str, str]:
    """Map each advertised OData property name to its original field name.

    ``business_key`` maps to itself; every declared field maps to its
    original name under its OData identifier.
    """
    properties: dict[str, str] = {"business_key": "business_key"}
    for field in fields:
        properties[odata_identifier(field["name"])] = field["name"]
    return properties


def _property_edm_type(property_name: str, fields: list[dict]) -> str:
    """Return the Edm type for an advertised property name."""
    if property_name == "business_key":
        return "Edm.String"
    for field in fields:
        if odata_identifier(field["name"]) == property_name:
            return edm_type_for(field.get("data_type"))
    return "Edm.String"


def _coerce_sort_value(value, edm_type: str):
    """Coerce a payload value to a sortable value for its Edm type family.

    Returns ``None`` when the value is ``None`` or the conversion fails.
    """
    if value is None:
        return None
    try:
        if edm_type in _NUMERIC_EDM_TYPES:
            return Decimal(str(value))
        if edm_type in _DATE_EDM_TYPES:
            text = str(value)
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            if "T" not in text:
                text = text + "T00:00:00+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        if edm_type == "Edm.Boolean":
            return bool(value)
        return str(value)
    except (TypeError, ValueError, ArithmeticError):
        return None


def _sort_key(value, edm_type: str):
    """Build the (is_none, coerced) sort key for one property value."""
    coerced = _coerce_sort_value(value, edm_type)
    return (coerced is None, coerced)


def _parse_select(raw: str, properties: dict[str, str]) -> list[str] | None:
    """Parse a ``$select`` option into an ordered list of property names.

    Returns ``None`` (with the offending item named) when an item is empty or
    not an advertised property.
    """
    selected: list[str] = []
    for item in raw.split(","):
        name = item.strip()
        if not name or name not in properties:
            return None
        selected.append(name)
    return selected


def _parse_orderby(
    raw: str, properties: dict[str, str]
) -> list[tuple[str, bool]] | None:
    """Parse an ``$orderby`` option into ``(property, descending)`` pairs.

    Returns ``None`` (with the offending item named) when an item is empty,
    the property is unknown, the direction is not asc/desc, or there are
    extra tokens.
    """
    items: list[tuple[str, bool]] = []
    for item in raw.split(","):
        tokens = item.split()
        if not tokens:
            return None
        property_name = tokens[0]
        if property_name not in properties:
            return None
        descending = False
        if len(tokens) > 1:
            if len(tokens) > 2:
                return None
            direction = tokens[1].lower()
            if direction not in ("asc", "desc"):
                return None
            descending = direction == "desc"
        items.append((property_name, descending))
    return items


@router.get("")
@router.get("/")
def service_document(
    request: Request,
    _credential: dict = Depends(require_feed_credential),
):
    """Return the OData v4 service document.

    One entry per dataset, keyed by the entity-set name produced by
    :func:`entity_set_names`.
    """
    datasets = _load_datasets()
    sets = entity_set_names(datasets)
    base_url = str(request.base_url).rstrip("/")
    value = [
        {"name": set_name, "kind": "EntitySet", "url": set_name} for set_name in sets
    ]
    return JSONResponse(
        content={
            "@odata.context": f"{base_url}/api/feed/v4/$metadata",
            "value": value,
        },
        headers=_odata_headers(),
    )


@router.get("/$metadata")
def metadata_document(
    _credential: dict = Depends(require_feed_credential),
):
    """Return the CSDL 4.0 EDMX metadata document as ``application/xml``."""
    datasets = _load_datasets()
    sets = entity_set_names(datasets)

    entity_types: list[str] = []
    entity_sets: list[str] = []
    for set_name, dataset_id in sets.items():
        fields = _load_fields(dataset_id)
        properties = [
            '        <Property Name="business_key" Type="Edm.String" Nullable="false"/>'
        ]
        for field in fields:
            prop_name = odata_identifier(field["name"])
            prop_type = edm_type_for(field.get("data_type"))
            properties.append(
                f'        <Property Name="{_xml_escape(prop_name)}" '
                f'Type="{_xml_escape(prop_type)}" Nullable="true"/>'
            )
        entity_types.append(
            '    <EntityType Name="' + _xml_escape(set_name) + '">'
            "\n"
            "      <Key>\n"
            '        <PropertyRef Name="business_key"/>\n'
            "      </Key>\n" + "\n".join(properties) + "\n"
            "    </EntityType>"
        )
        entity_sets.append(
            '    <EntitySet Name="'
            + _xml_escape(set_name)
            + '" EntityType="AIDW.'
            + _xml_escape(set_name)
            + '"/>'
        )

    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">\n'
        "  <edmx:DataServices>\n"
        '    <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="AIDW">\n'
        + "\n".join(entity_types)
        + "\n"
        "    </Schema>\n"
        '    <EntityContainer Name="Container">\n' + "\n".join(entity_sets) + "\n"
        "    </EntityContainer>\n"
        "  </edmx:DataServices>\n"
        "</edmx:Edmx>\n"
    )
    return Response(
        content=xml,
        media_type="application/xml",
        headers=_odata_headers(),
    )


@router.get("/{entity_set}")
def read_entity_set(
    entity_set: str,
    request: Request,
    _credential: dict = Depends(require_feed_credential),
):
    """Return the ingested payloads for a dataset as OData v4 entities.

    The set is resolved through :func:`entity_set_names` over the datasets
    rows. Each ingested payload is rendered with ``business_key`` plus one
    property per declared discovered field (property name is the OData
    identifier of the field name, value looked up by the original field name
    in the JSONB payload). ``$select`` projects to the named properties in
    order; ``$orderby`` sorts the full set before paging.
    """
    datasets = _load_datasets()
    sets = entity_set_names(datasets)
    dataset_id = sets.get(entity_set)
    if dataset_id is None:
        return _odata_error(404, f"Entity set '{entity_set}' not found.")

    # Reject any unsupported system query option before doing any work.
    for key in request.query_params:
        if key.startswith("$") and key not in _SUPPORTED_QUERY_OPTIONS:
            return _odata_error(501, f"Query option '{key}' is not supported.")

    page_size = _page_size()

    top_raw = request.query_params.get("$top")
    top: int | None = None
    if top_raw is not None:
        parsed = _parse_int_option(top_raw)
        if parsed is None:
            return _odata_error(
                400, "Query option '$top' must be a non-negative integer."
            )
        top = min(parsed, page_size)

    skip_raw = request.query_params.get("$skip")
    skip = 0
    if skip_raw is not None:
        parsed = _parse_int_option(skip_raw)
        if parsed is None:
            return _odata_error(
                400, "Query option '$skip' must be a non-negative integer."
            )
        skip = parsed

    count = request.query_params.get("$count", "").lower() == "true"

    fields = _load_fields(dataset_id)
    payloads = _load_payloads(dataset_id)

    properties = _advertised_properties(fields)

    select_raw = request.query_params.get("$select")
    selected: list[str] | None = None
    if select_raw is not None:
        selected = _parse_select(select_raw, properties)
        if selected is None:
            for item in select_raw.split(","):
                name = item.strip()
                if not name or name not in properties:
                    return _odata_error(
                        400,
                        f"Query option '$select' item '{name}' is not an "
                        "advertised property.",
                    )

    orderby_raw = request.query_params.get("$orderby")
    order_items: list[tuple[str, bool]] | None = None
    if orderby_raw is not None:
        order_items = _parse_orderby(orderby_raw, properties)
        if order_items is None:
            for item in orderby_raw.split(","):
                tokens = item.split()
                if not tokens:
                    return _odata_error(
                        400, "Query option '$orderby' contains an empty item."
                    )
                property_name = tokens[0]
                if property_name not in properties:
                    return _odata_error(
                        400,
                        f"Query option '$orderby' item '{property_name}' is "
                        "not an advertised property.",
                    )
                if len(tokens) > 2:
                    return _odata_error(
                        400,
                        f"Query option '$orderby' item '{item}' has extra tokens.",
                    )
                if len(tokens) == 2 and tokens[1].lower() not in ("asc", "desc"):
                    return _odata_error(
                        400,
                        f"Query option '$orderby' item '{item}' has an invalid "
                        "direction.",
                    )

    total = len(payloads)

    if order_items:
        ordered = list(payloads)
        for property_name, descending in reversed(order_items):
            edm_type = _property_edm_type(property_name, fields)
            original = properties[property_name]

            def _key(row, _original=original, _edm_type=edm_type):
                payload = row.get("payload") or {}
                if _original == "business_key":
                    value = row.get("business_key")
                else:
                    value = payload.get(_original)
                return _sort_key(value, _edm_type)

            ordered.sort(key=_key, reverse=descending)
        payloads = ordered

    page = payloads[skip : skip + page_size]
    if top is not None:
        page = page[:top]

    value = []
    for row in page:
        payload = row.get("payload") or {}
        if selected is None:
            entity: dict = {"business_key": row.get("business_key")}
            for field in fields:
                original = field["name"]
                entity[odata_identifier(original)] = payload.get(original)
        else:
            entity = {}
            for property_name in selected:
                original = properties[property_name]
                if original == "business_key":
                    entity[property_name] = row.get("business_key")
                else:
                    entity[property_name] = payload.get(original)
        value.append(entity)

    base_url = str(request.base_url).rstrip("/")
    body: dict = {
        "@odata.context": f"{base_url}/api/feed/v4/$metadata#{entity_set}",
        "value": value,
    }
    if count:
        body["@odata.count"] = total
    if len(page) > 0 and skip + len(page) < total:
        body["@odata.nextLink"] = _build_next_link(
            base_url,
            entity_set,
            skip + len(page),
            top,
            count,
            select=select_raw,
            orderby=orderby_raw,
        )

    return JSONResponse(
        content=body,
        media_type="application/json;odata.metadata=minimal",
        headers=_odata_headers(),
    )
