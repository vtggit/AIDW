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

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.db.connection import get_cursor
from app.feed.auth import require_feed_credential
from app.feed.naming import edm_type_for, entity_set_names, odata_identifier

router = APIRouter(prefix="/api/feed/v4", tags=["feed-odata"])

_ODATA_VERSION = "4.0"

# System query options the entity-set read understands. Anything else that
# starts with ``$`` is rejected with 501.
_SUPPORTED_QUERY_OPTIONS = {"$top", "$skip", "$count"}


def _odata_headers() -> dict[str, str]:
    """Headers every feed response must carry."""
    return {"OData-Version": _ODATA_VERSION}


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
    base_url: str, set_name: str, skip: int, top: int | None, count: bool
) -> str:
    """Build the ``@odata.nextLink`` for the next page of a set read."""
    parts = [f"{base_url}/api/feed/v4/{set_name}?$skip={skip}"]
    if top is not None:
        parts.append(f"&$top={top}")
    if count:
        parts.append("&$count=true")
    return "".join(parts)


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
    in the JSONB payload). Undeclared payload keys are dropped and values are
    emitted as landed, with no coercion.
    """
    datasets = _load_datasets()
    sets = entity_set_names(datasets)
    dataset_id = sets.get(entity_set)
    if dataset_id is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "404",
                    "message": f"Entity set '{entity_set}' not found.",
                }
            },
            headers=_odata_headers(),
        )

    # Reject any unsupported system query option before doing any work.
    for key in request.query_params:
        if key.startswith("$") and key not in _SUPPORTED_QUERY_OPTIONS:
            return JSONResponse(
                status_code=501,
                content={
                    "error": {
                        "code": "501",
                        "message": f"Query option '{key}' is not supported.",
                    }
                },
                headers=_odata_headers(),
            )

    page_size = _page_size()

    top_raw = request.query_params.get("$top")
    top: int | None = None
    if top_raw is not None:
        parsed = _parse_int_option(top_raw)
        if parsed is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "400",
                        "message": "Query option '$top' must be a non-negative integer.",
                    }
                },
                headers=_odata_headers(),
            )
        top = min(parsed, page_size)

    skip_raw = request.query_params.get("$skip")
    skip = 0
    if skip_raw is not None:
        parsed = _parse_int_option(skip_raw)
        if parsed is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "400",
                        "message": "Query option '$skip' must be a non-negative integer.",
                    }
                },
                headers=_odata_headers(),
            )
        skip = parsed

    count = request.query_params.get("$count", "").lower() == "true"

    fields = _load_fields(dataset_id)
    payloads = _load_payloads(dataset_id)

    total = len(payloads)
    page = payloads[skip : skip + page_size]
    if top is not None:
        page = page[:top]

    value = []
    for row in page:
        payload = row.get("payload") or {}
        entity: dict = {"business_key": row.get("business_key")}
        for field in fields:
            original = field["name"]
            entity[odata_identifier(original)] = payload.get(original)
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
            base_url, entity_set, skip + len(page), top, count
        )

    return JSONResponse(
        content=body,
        media_type="application/json;odata.metadata=minimal",
        headers=_odata_headers(),
    )
