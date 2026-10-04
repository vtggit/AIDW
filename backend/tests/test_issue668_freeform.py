"""Issue 668 — the backend is the authority for API access control.

Proves the ``PUBLIC_API_ROUTES`` allowlist and its CI guard
(``app.auth.public_routes``):

* walks every ``/api`` route of the served application
  (``app.main.app``), including routes mounted through included
  routers, and asserts each ``(method, path)`` pair is either an exact
  ``PUBLIC_API_ROUTES`` entry or reaches a known authentication
  dependency (a ``require_*`` dependency from ``app.auth.dependencies``
  or the feed-credential dependency from ``app.feed.auth``) somewhere
  in its resolved dependency tree;
* asserts every ``PUBLIC_API_ROUTES`` entry still exists in the served
  app (no stale allowlist entries);
* mounts rogue routers on a fresh copy of the app and asserts the
  guard reports each unauthenticated route **by name** — including
  routes whose only "auth" is an inert helper named like an auth
  factory — while factory-produced auth dependencies
  (``require_role`` / ``require_any_role``) keep legitimate protected
  routes passing;
* proves recognition is by **identity**, not equality: a crafted
  callable that compares equal to (and hashes like) a known
  authentication dependency is still inert, while the genuine object
  is recognised;
* proves the guard walks **mounted sub-applications**: unauthenticated
  routes served through ``app.mount(prefix, sub_app)`` are reported by
  name at their prefixed paths (including nested mounts and routers
  included inside the sub-app), while authenticated routes inside the
  sub-app keep passing.
"""

import types

from fastapi import APIRouter, Depends, FastAPI

from app.auth.authorization import require_any_role, require_role
from app.auth.dependencies import get_current_user, require_authenticated_user
from app.auth.public_routes import (
    AUTH_DEPENDENCY_OBJECTS,
    PUBLIC_API_ROUTES,
    find_auth_dependency,
    is_public_route,
    iter_api_route_entries,
    missing_allowlist_entries,
    unauthenticated_api_routes,
)
from app.feed.auth import require_feed_credential
from app.main import app as served_app
from app.main import create_app


class _LookalikeAuthDependency:
    """A crafted callable that *compares equal* to a real auth dependency.

    ``hash`` and ``__eq__`` are forged to match the target, so any
    recognition built on set membership / equality accepts it — while
    identity (``is``) correctly rejects it.
    """

    def __init__(self, target):
        self._target = target

    def __eq__(self, other):
        return other is self._target

    def __hash__(self):
        return hash(self._target)

    def __call__(self):
        return None


class _FakeDependant:
    """Minimal stand-in for a FastAPI dependant: a list of calls."""

    def __init__(self, calls):
        self.dependencies = [
            types.SimpleNamespace(path="/", call=call) for call in calls
        ]


def test_issue668_freeform():
    # The identity set the guard uses must be exactly the two known
    # authentication dependency objects — nothing more is accepted.
    assert {
        require_authenticated_user,
        require_feed_credential,
    } == AUTH_DEPENDENCY_OBJECTS

    # ------------------------------------------------------------------
    # Recognition is identity, not equality: a forged lookalike that
    # compares equal to and hashes like the real dependency must NOT
    # be accepted, while the genuine object is.
    # ------------------------------------------------------------------
    lookalike = _LookalikeAuthDependency(require_authenticated_user)
    assert lookalike is not require_authenticated_user
    assert lookalike == require_authenticated_user
    assert hash(lookalike) == hash(require_authenticated_user)
    # Set equality would accept the forgery (the defect under proof)...
    assert lookalike in {
        require_authenticated_user,
        require_feed_credential,
    }
    # ...but the guard recognises by identity and rejects it.
    assert find_auth_dependency(_FakeDependant([lookalike])) is None
    # ...and accepts the genuine object.
    assert (
        find_auth_dependency(_FakeDependant([require_authenticated_user]))
        is require_authenticated_user
    )
    assert (
        find_auth_dependency(_FakeDependant([require_feed_credential]))
        is require_feed_credential
    )

    # ------------------------------------------------------------------
    # Served application: every /api (method, path) pair is either an
    # exact allowlist entry or reaches a known auth dependency.
    # ------------------------------------------------------------------
    entries = list(iter_api_route_entries(served_app))
    api_pairs = {(entry.method, entry.path) for entry in entries}
    assert api_pairs, "expected /api routes on the served app"
    assert api_pairs >= PUBLIC_API_ROUTES, "served app lost a public route"

    for entry in entries:
        if is_public_route(entry.method, entry.path):
            continue
        auth = find_auth_dependency(entry.dependant)
        assert auth is not None, (
            f"{entry.method} {entry.path} (route {entry.name!r}) has no "
            "authentication dependency and is not in PUBLIC_API_ROUTES"
        )
        # The covering dependency is either a require_* dependency from
        # app.auth.dependencies or the feed-credential dependency from
        # app.feed.auth.
        assert (
            auth.__module__ == "app.auth.dependencies"
            and auth.__name__.startswith("require_")
        ) or auth is require_feed_credential, (
            f"{entry.method} {entry.path} is covered by an unexpected "
            f"dependency {auth!r}"
        )

    # The guard itself must accept the whole served app...
    assert unauthenticated_api_routes(served_app) == []
    # ...and no allowlist entry may be stale.
    assert missing_allowlist_entries(served_app) == []

    # ------------------------------------------------------------------
    # Fresh copy of the app: a router mounted without any auth
    # dependency is reported by name, inert helpers are rejected, and
    # factory-produced auth dependencies keep protected routes passing.
    # ------------------------------------------------------------------
    fresh = create_app()

    def inert_require_admin():
        # Inert helper deliberately named like an auth factory (and not
        # defined in any auth module): it must NOT count as auth, no
        # matter how its name or qualname looks.
        return None

    rogue = APIRouter(tags=["issue668-rogue"])

    @rogue.get("/api/rogue/open")
    def rogue_open() -> dict:
        return {}

    @rogue.get("/api/rogue/inert")
    def inert_admin(_gate: None = Depends(inert_require_admin)) -> dict:
        return {}

    @rogue.get("/api/rogue/optional")
    def optional_user(_user: object = Depends(get_current_user)) -> dict:
        return {}

    @rogue.api_route("/api/rogue/multi", methods=["GET", "POST"])
    def multi_open() -> dict:
        return {}

    @rogue.post("/api/health")
    def post_health() -> dict:
        # The allowlist holds exact (method, path) pairs: only
        # GET /api/health is public, so POST /api/health is not.
        return {}

    fresh.include_router(rogue)

    protected = APIRouter(tags=["issue668-protected"])

    @protected.get(
        "/api/rogue/by-role",
        dependencies=[Depends(require_role("admin"))],
    )
    def protected_by_role() -> dict:
        return {}

    @protected.get("/api/rogue/by-any-role")
    def protected_by_any_role(
        _user: object = Depends(require_any_role(["admin", "user"])),
    ) -> dict:
        return {}

    @protected.get("/api/rogue/direct")
    def protected_direct(
        _user: object = Depends(require_authenticated_user),
    ) -> dict:
        return {}

    @protected.get("/api/rogue/feed")
    def protected_feed(
        _credential: dict = Depends(require_feed_credential),
    ) -> dict:
        return {}

    fresh.include_router(protected)

    reported = unauthenticated_api_routes(fresh)
    reported_names = {entry.name for entry in reported}
    reported_pairs = {(entry.method, entry.path) for entry in reported}

    # Every unauthenticated route is reported, by name.
    for name in (
        "rogue_open",
        "inert_admin",
        "optional_user",
        "multi_open",
        "post_health",
    ):
        assert name in reported_names, f"route {name!r} was not reported by name"

    # The guard rejects exactly the expected (method, path) pairs:
    # multi-method routes are expanded per method, and the allowlist
    # matches pairs exactly (POST /api/health is not public).
    assert reported_pairs == {
        ("GET", "/api/rogue/open"),
        ("GET", "/api/rogue/inert"),
        ("GET", "/api/rogue/optional"),
        ("GET", "/api/rogue/multi"),
        ("POST", "/api/rogue/multi"),
        ("POST", "/api/health"),
    }

    # Factory-produced and direct auth dependencies keep the
    # legitimate protected routes passing — no false failures.
    assert not reported_pairs & {
        ("GET", "/api/rogue/by-role"),
        ("GET", "/api/rogue/by-any-role"),
        ("GET", "/api/rogue/direct"),
        ("GET", "/api/rogue/feed"),
    }

    # ------------------------------------------------------------------
    # Mounted sub-applications are walked too: their /api routes must
    # be evaluated at their prefixed paths (nested mounts and routers
    # included inside the sub-app compose the prefix as well).
    # ------------------------------------------------------------------
    inner = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @inner.get("/deep")
    def sub_deep() -> dict:
        return {}

    sub_app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @sub_app.get("/open")
    def sub_open() -> dict:
        return {}

    @sub_app.get("/guarded")
    def sub_guarded(_user: object = Depends(require_authenticated_user)) -> dict:
        return {}

    sub_router = APIRouter(prefix="/router", tags=["issue668-sub-router"])

    @sub_router.get(
        "/authed",
        dependencies=[Depends(require_role("admin"))],
    )
    def sub_router_authed() -> dict:
        return {}

    sub_app.include_router(sub_router)
    sub_app.mount("/deep", inner)
    fresh.mount("/api/sub", sub_app)

    reported = unauthenticated_api_routes(fresh)
    reported_names = {entry.name for entry in reported}
    reported_pairs = {(entry.method, entry.path) for entry in reported}

    # Unauthenticated routes inside the sub-app (direct, nested mount,
    # and multi-level prefix composition) are reported by name.
    for name in ("sub_open", "sub_deep"):
        assert name in reported_names, (
            f"route {name!r} served through a mounted sub-app was not "
            "reported by name"
        )
    assert ("GET", "/api/sub/open") in reported_pairs
    assert ("GET", "/api/sub/deep/deep") in reported_pairs
    # Authenticated routes inside the sub-app keep passing (no
    # false failures), including factory dependencies on routers
    # included inside the sub-app.
    assert not reported_pairs & {
        ("GET", "/api/sub/guarded"),
        ("GET", "/api/sub/router/authed"),
    }
    # The complete offender set after mounting the sub-app: the rogue
    # routes plus exactly the two unauthenticated sub-app routes.
    assert reported_pairs == {
        ("GET", "/api/rogue/open"),
        ("GET", "/api/rogue/inert"),
        ("GET", "/api/rogue/optional"),
        ("GET", "/api/rogue/multi"),
        ("POST", "/api/rogue/multi"),
        ("POST", "/api/health"),
        ("GET", "/api/sub/open"),
        ("GET", "/api/sub/deep/deep"),
    }

    # Stale-entry detection: an app serving none of the public routes
    # must report every allowlist entry as missing.
    bare = FastAPI()
    assert missing_allowlist_entries(bare) == sorted(PUBLIC_API_ROUTES)
