import os
import subprocess
import sys


def _run_config_check(env_overrides: dict[str, str | None]) -> str:
    """Run app.auth.config in a fresh subprocess and return AUTH_JWKS_URL."""
    env = os.environ.copy()
    env["AUTH_ISSUER"] = "https://idp.example.test/realms/demo"
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value

    code = "from app.auth.config import AUTH_JWKS_URL; print(AUTH_JWKS_URL)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return result.stdout.strip()


def test_issue789_surgical():
    # Case 1: AUTH_JWKS_URL set to empty string → falls back to default
    url = _run_config_check({"AUTH_JWKS_URL": ""})
    assert url == ("https://idp.example.test/realms/demo/protocol/openid-connect/certs")

    # Case 2: AUTH_JWKS_URL removed from environment → falls back to default
    url = _run_config_check({"AUTH_JWKS_URL": None})
    assert url == ("https://idp.example.test/realms/demo/protocol/openid-connect/certs")

    # Case 3: AUTH_JWKS_URL set to a real value → used as given
    url = _run_config_check({"AUTH_JWKS_URL": "https://keys.example.test/certs"})
    assert url == "https://keys.example.test/certs"
