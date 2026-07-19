"""flowable sidecar client (engine-generated: sidecar-proxy lane).

Configuration is ENV-ONLY — the ratified allowlist boundary (AIDW#189): the
engine base URL and credentials come exclusively from the environment, never
from request payloads or source literals.

  FLOWABLE_BASE_URL       e.g. http://flowable:8080/flowable-rest/service
  FLOWABLE_REST_USER      REST basic-auth user
  FLOWABLE_REST_PASSWORD  REST basic-auth password
"""

import os

import httpx

_TIMEOUT = 15.0


class SidecarConfigError(RuntimeError):
    """Sidecar env config is missing — fail closed (the router maps this to 503)."""


def _config():
    base = os.environ.get("FLOWABLE_BASE_URL", "").rstrip("/")
    user = os.environ.get("FLOWABLE_REST_USER", "")
    password = os.environ.get("FLOWABLE_REST_PASSWORD", "")
    if not base or not user or not password:
        raise SidecarConfigError(
            "flowable sidecar is not configured "
            "(FLOWABLE_BASE_URL/_REST_USER/_REST_PASSWORD)"
        )
    return base, (user, password)


async def start_process(process_key: str, variables: dict) -> str:
    """Start a process instance; returns the engine instance id.

    ``variables`` arrive PRE-VALIDATED by the router's allowlist model —
    opaque references only, never subject data (AIDW#189 OQ-6)."""
    base, auth = _config()
    payload = {
        "processDefinitionKey": process_key,
        "variables": [{"name": k, "value": v} for k, v in variables.items()],
    }
    async with httpx.AsyncClient(auth=auth, timeout=_TIMEOUT) as client:
        resp = await client.post(base + "/runtime/process-instances", json=payload)
        resp.raise_for_status()
        return resp.json()["id"]


async def get_instance(instance_id: str):
    """Historic-instance lookup (covers running AND ended); None on 404."""
    base, auth = _config()
    async with httpx.AsyncClient(auth=auth, timeout=_TIMEOUT) as client:
        resp = await client.get(
            base + "/history/historic-process-instances/" + instance_id
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


async def purge_instance(instance_id: str) -> bool:
    """Erase the historic instance + all its variables/tasks/details in one
    call (the RTBF audit-close purge, AIDW#189 OQ-2); False if already gone."""
    base, auth = _config()
    async with httpx.AsyncClient(auth=auth, timeout=_TIMEOUT) as client:
        resp = await client.delete(
            base + "/history/historic-process-instances/" + instance_id
        )
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True
