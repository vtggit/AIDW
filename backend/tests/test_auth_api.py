"""Auth API tests.

Verifies authentication behavior:
    - /api/auth/me returns 401 without token
    - Valid dev token returns authenticated user context
    - Invalid token returns 401
    - Role/group normalization works for expected token shapes
"""


def test_auth_me_without_token_returns_401(client):
    """GET /api/auth/me without Authorization header should return 401."""
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_auth_me_with_invalid_token_returns_401(client):
    """GET /api/auth/me with an invalid token should return 401."""
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer obviously-invalid-token"},
    )
    assert response.status_code == 401


def test_auth_me_with_valid_admin_token_returns_200(client, admin_token):
    """GET /api/auth/me with a valid admin token should return 200 and user context."""
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    # Response shape: {"authenticated": True, "user": {sub, username, email, roles, groups, raw_claims}}
    assert data.get("authenticated") is True
    user = data.get("user", {})
    assert user.get("email") or user.get("username") or user.get("sub")


def test_auth_me_with_valid_user_token_returns_200(client, user_token):
    """GET /api/auth/me with a valid user token should return 200."""
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 200


def test_auth_me_admin_token_has_admin_role(client, admin_token):
    """Admin token should include admin in roles/groups."""
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = response.json()
    user = data.get("user", {})
    roles = user.get("roles", []) + user.get("groups", [])
    role_names = [r.lower() if isinstance(r, str) else str(r).lower() for r in roles]
    assert "admin" in role_names


def test_auth_me_user_token_does_not_have_admin_role(client, user_token):
    """Non-admin user token should not include admin role."""
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    data = response.json()
    user = data.get("user", {})
    roles = user.get("roles", []) + user.get("groups", [])
    role_names = [r.lower() if isinstance(r, str) else str(r).lower() for r in roles]
    assert "admin" not in role_names
