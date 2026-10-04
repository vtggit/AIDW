"""Public (unauthenticated) API route allowlist for the AIDW backend.

Policy:

* The backend is the authority for access control.  An API route is
  served without authentication **only** when its exact ``(method,
  path)`` pair is listed in :data:`PUBLIC_API_ROUTES`; every other
  ``/api`` route must carry authentication in its resolved dependency
  graph (a known authentication dependency, directly or via a
  dependency whose own graph reaches one).
* The frontend boot gate is a UX convenience only — it shapes the
  anonymous experience but never grants or denies access.  Nothing the
  frontend does overrides the checks enforced by this module.
* Any addition to :data:`PUBLIC_API_ROUTES` is a security decision that
  must be made deliberately in review.  The CI guard
  (``tests/test_issue668_freeform.py``) walks every ``/api`` route of
  the served application and fails the build when a route is neither
  listed here nor reachable from a known authentication dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.dependencies.utils import get_dependant
from fastapi.routing import APIRoute

from app.auth.dependencies import require_authenticated_user
from app.feed.auth import require_feed_credential

#: Exact ``(method, path)`` pairs that may be served without
#: authentication.  A route is public only when its method and path
#: exactly match one of these entries — no prefixes, wildcards, or
#: case-insensitive matching.
PUBLIC_API_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/health/ready"),
        ("GET", "/api/health/version"),
        ("GET", "/api/auth/config"),
    }
)

#: The only dependency objects the guard recognises as authentication.
#: Membership tests are by **object identity**: renaming, re-binding or
#: shadowing one of these functions changes nothing — only these exact
#: objects count, and nothing is accepted by name, prefix, qualname or
#: module.
AUTH_DEPENDENCY_OBJECTS: frozenset = frozenset(
    {
        require_authenticated_user,
        require_feed_credential,
    }
)


@dataclass(frozen=True)
class APIRouteEntry:
    """One ``(method, path)`` pair of a served ``/api`` route.

    ``dependant`` is the FastAPI dependency graph FastAPI actually
    executes for the route (route-level ``dependencies=`` plus every
    ``Depends(...)`` in parameter signatures, with include-level
    dependencies merged in for routes mounted through routers).
    ``name`` is the FastAPI route name — the endpoint function name —
    so offenders are reported by name.
    """

    method: str
    path: str
    dependant: object
    name: str


def is_public_route(method: str, path: str) -> bool:
    """Return True only when ``(method, path)`` exactly matches an allowlist entry."""
    return (method, path) in PUBLIC_API_ROUTES


def iter_api_route_entries(app: FastAPI):
    """Yield an :class:`APIRouteEntry` for every ``/api`` route of ``app``.

    Walks the routes attached to the application directly, the routes
    mounted through included routers (including nested
    ``include_router`` chains) and the routes served through mounted
    sub-applications (``app.mount(prefix, sub_app)`` — including
    sub-apps that themselves include routers or mount further
    sub-apps, with the mount prefix applied to their paths).  For each
    :class:`APIRoute` every method the route declares is expanded, so
    a route registered for GET and POST yields one entry per method —
    each resulting ``(method, path)`` pair is evaluated independently.
    """
    yield from _iter_route_entries(app.routes, path_prefix="", chain={id(app)})


def _iter_route_entries(routes, path_prefix: str, chain: set[int]):
    for route in routes:
        if isinstance(route, APIRoute):
            entries = _route_entries(
                path_prefix + route.path, route.methods, route.dependant, route.name
            )
            yield from _filter_api(entries)
            continue
        # Routes behind included routers are kept as wrapper entries
        # (FastAPI >= 0.119); their effective route contexts carry the
        # final prefixed path (relative to the app that owns the
        # wrapper), the declared methods and the merged (include-level
        # + route-level) dependant.
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            for context in contexts():
                original = getattr(context, "original_route", None)
                if not isinstance(original, APIRoute):
                    continue
                path = path_prefix + (getattr(context, "path", "") or original.path)
                dependant = getattr(context, "dependant", None)
                if dependant is None:
                    dependant = original.dependant
                methods = getattr(context, "methods", None) or original.methods
                name = getattr(context, "name", "") or original.name
                entries = _route_entries(path, methods, dependant, name)
                yield from _filter_api(entries)
            continue
        # Mounted sub-applications (starlette ``Mount``): recurse into
        # the sub-app's routes with the mount path as the new prefix.
        # The ancestry ``chain`` guards against cyclic mounts.
        sub_app = getattr(route, "app", None)
        if (
            sub_app is not None
            and sub_app is not route
            and hasattr(sub_app, "routes")
            and id(sub_app) not in chain
        ):
            yield from _iter_route_entries(
                sub_app.routes,
                path_prefix=path_prefix + (getattr(route, "path", "") or ""),
                chain=chain | {id(sub_app)},
            )


def _route_entries(path: str, methods: set[str], dependant: object, name: str):
    for method in sorted(methods):
        yield APIRouteEntry(method=method, path=path, dependant=dependant, name=name)


def _filter_api(entries):
    for entry in entries:
        if entry.path.startswith("/api"):
            yield entry


def _iter_dependency_calls(dependant: object):
    """Yield every callable in the resolved dependency graph of ``dependant``.

    The walk follows ``Depends(...)`` declarations transitively: each
    dependency's own parameters are resolved with
    ``fastapi.dependencies.utils.get_dependant`` — the same mechanism
    FastAPI uses at request time — so factory closures such as
    ``require_role("admin")`` expand to the ``require_authenticated_user``
    dependency declared in their signature.

    A dependency whose signature cannot be resolved contributes no
    further calls; the guard can then not prove authentication from it,
    so the route fails closed.
    """
    seen: set[int] = set()
    stack: list = list(dependant.dependencies)
    while stack:
        sub = stack.pop()
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        yield sub.call
        try:
            expanded = get_dependant(
                path=getattr(sub, "path", "") or "/", call=sub.call
            )
        except Exception:
            continue
        stack.extend(expanded.dependencies)


def _is_known_auth_dependency(call: object) -> bool:
    """Return True only when ``call`` *is* one of the known auth dependencies.

    The test is object identity (``is``), not set membership or equality:
    a crafted callable that merely compares equal to a known dependency
    object (matching ``__hash__``/``__eq__``) is not the dependency and
    is inert.
    """
    return any(call is known for known in AUTH_DEPENDENCY_OBJECTS)


def find_auth_dependency(dependant: object):
    """Return the first known authentication dependency in ``dependant``'s graph.

    Returns one of :data:`AUTH_DEPENDENCY_OBJECTS` when the resolved
    dependency graph reaches it, or ``None`` when it does not.

    Recognition is by the identity of the known authentication
    dependency objects (``is``, never ``==``), or by equivalent
    provenance: a dependency whose own resolved graph reaches one of
    them (e.g. the closures returned by ``require_role`` /
    ``require_any_role``).  Dependency names, prefixes, qualnames and
    module paths are never consulted, so a helper merely named like an
    auth factory — or imported from an allowlist-looking module — is
    inert and never counts.
    """
    for call in _iter_dependency_calls(dependant):
        if _is_known_auth_dependency(call):
            return call
    return None


def unauthenticated_api_routes(app: FastAPI) -> list[APIRouteEntry]:
    """Return every ``/api`` (method, path) pair that the guard rejects.

    A route is accepted when its ``(method, path)`` pair exactly
    matches an entry of :data:`PUBLIC_API_ROUTES`, or when its resolved
    dependency graph reaches a known authentication dependency (directly
    or through a dependency whose own graph reaches one).  Everything
    else is reported, by name, as an :class:`APIRouteEntry`.
    """
    offenders: list[APIRouteEntry] = []
    for entry in iter_api_route_entries(app):
        if (entry.method, entry.path) in PUBLIC_API_ROUTES:
            continue
        if find_auth_dependency(entry.dependant) is None:
            offenders.append(entry)
    return offenders


def missing_allowlist_entries(app: FastAPI) -> list[tuple[str, str]]:
    """Return :data:`PUBLIC_API_ROUTES` entries that no route in ``app`` serves.

    Stale allowlist entries are a security smell — a public route that
    no longer exists may be reintroduced later without anyone noticing
    it was ever allowlisted.
    """
    served = {(entry.method, entry.path) for entry in iter_api_route_entries(app)}
    return sorted(entry for entry in PUBLIC_API_ROUTES if entry not in served)
