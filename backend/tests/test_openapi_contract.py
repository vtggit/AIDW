"""Contract-oriented tests for the OpenAPI schema.

These tests verify that the generated OpenAPI schema is structurally sound
and that critical endpoints expose the expected schema components.  They do
not replace the CI diff check (which catches drift); they catch broken
generation and missing route registration.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client():
    """Create a test client from a fresh app instance."""
    return TestClient(create_app())


class TestOpenAPISchemaGeneration:
    """Ensure the OpenAPI schema is valid and contains expected structure."""

    def test_openapi_schema_is_valid_json(self, client: TestClient):
        """The /openapi.json endpoint must return valid JSON."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert isinstance(schema, dict)
        assert "openapi" in schema
        assert "paths" in schema
        assert "components" in schema

    def test_critical_paths_are_registered(self, client: TestClient):
        """All domain endpoints must appear in the OpenAPI schema."""
        schema = client.get("/openapi.json").json()
        paths = list(schema["paths"].keys())

        expected = [
            "/api/health",
            "/api/auth/me",
            "/api/auth/config",
            "/api/contacts",
            "/api/contacts/{contact_id}",
            "/api/templates",
            "/api/templates/{template_id}",
            "/api/leads",
            "/api/leads/{lead_id}",
            "/api/activities",
            "/api/activities/{activity_id}",
            "/api/settings",
            "/api/audit",
        ]

        for path in expected:
            assert path in paths, f"Expected path {path} not found in OpenAPI schema"

    def test_response_schemas_exist(self, client: TestClient):
        """Key response models must be present in the component schemas."""
        schema = client.get("/openapi.json").json()
        schemas = schema["components"]["schemas"]

        expected_schemas = [
            "ContactResponse",
            "TemplateResponse",
            "LeadResponse",
            "ActivityResponse",
            "SettingsResponse",
            "AuditEventResponse",
            "MeResponse",
            "HealthResponse",
            "AuthConfigResponse",
        ]

        for name in expected_schemas:
            assert (
                name in schemas
            ), f"Expected schema {name} not found in OpenAPI components"

    def test_committed_artifact_matches_generated_schema(self, client: TestClient):
        """The committed openapi.json must match the live schema."""
        live_schema = client.get("/openapi.json").json()
        artifact_path = "openapi.json"

        try:
            with open(artifact_path) as f:
                committed_schema = json.load(f)
        except FileNotFoundError:
            pytest.fail(
                f"Contract artifact not found at {artifact_path}. Run: python3 scripts/export_openapi.py"
            )

        assert live_schema == committed_schema, (
            "Live OpenAPI schema differs from committed artifact. "
            "Regenerate with: python3 scripts/export_openapi.py"
        )
