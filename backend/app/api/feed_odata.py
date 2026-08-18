"""OData v4 feed surface.

Exposes the discovered datasets as an OData v4 service: a service document at
the service root, and a CSDL 4.0 EDMX metadata document at ``/$metadata``.

This module performs no credential handling of its own — every route depends
on :func:`app.feed.auth.require_feed_credential`, and no Basic / X-Api-Key
parsing happens here.  Naming is delegated to :mod:`app.feed.naming`, and the
database is read only through :func:`app.db.connection.get_cursor`.  Every
response carries the ``OData-Version: 4.0`` header.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.db.connection import get_cursor
from app.feed.auth import require_feed_credential
from app.feed.naming import edm_type_for, entity_set_names, odata_identifier

router = APIRouter(prefix="/api/feed/v4", tags=["feed-odata"])

_ODATA_VERSION = "4.0"


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


def _xml_escape(value: str) -> str:
    """Escape a value for safe inclusion in XML text/attribute content."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


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
