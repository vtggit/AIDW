"""Issue #653 — Alembic started from backend/ must be able to import the app package.

The ``alembic`` console script (unlike ``python -m alembic``) does not put
the working directory on ``sys.path``, so with a bare ``alembic.ini`` the
``import app`` performed by env.py fails when migrations are started from
``backend/``.  ``prepend_sys_path = .`` in the ``[alembic]`` section fixes
that for every entry point, because ``ScriptDirectory.from_config`` prepends
the configured path to ``sys.path``.

Proves:

1. (AC-1) the checked-in ``backend/alembic.ini`` sets
   ``prepend_sys_path = .`` in its ``[alembic]`` section;
2. (AC-2) a subprocess running the interpreter in isolated mode
   (``sys.executable -I -c ...``, working directory ``backend/``,
   ``PYTHONPATH`` removed from the environment — like the console script,
   the working directory is not on ``sys.path``) executes
   ``from alembic.config import Config; from alembic.script import
   ScriptDirectory; ScriptDirectory.from_config(Config("alembic.ini"));
   import app`` and exits with code 0;
3. (AC-2, negative) the same probe against an ``alembic.ini`` without
   ``prepend_sys_path`` fails with ``ModuleNotFoundError: No module named
   'app'``.  The negative probe is isolated from any ``app`` package
   installed in the environment: a shadow module pinned to ``sys.path[0]``
   makes ``import app`` raise exactly that error, while a simulated
   installed app (an importable ``app`` package appended to the end of
   ``sys.path``, like site-packages) proves the isolation is load-bearing —
   a probe without the shadow imports the installed app and wrongly exits 0.
"""

import configparser
import os
import pathlib
import subprocess
import sys
import tempfile

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_ALEMBIC_INI = _BACKEND / "alembic.ini"

# The exact statement sequence AC-2 requires the isolated interpreter to run.
_PROBE = (
    "from alembic.config import Config; "
    "from alembic.script import ScriptDirectory; "
    'ScriptDirectory.from_config(Config("alembic.ini")); '
    "import app"
)

# Shadow module the negative probe pins to sys.path[0]: `import app` executes
# it and fails with the very error the negative probe must produce, no matter
# which app packages are importable from site-packages or elsewhere.
_SHADOW_SOURCE = "raise ModuleNotFoundError(\"No module named 'app'\")\n"

# Marker of the simulated installed app (an importable stand-in for an app
# package a `pip install` would place in site-packages).
_SIMULATED_MARKER = "issue653-simulated-installed-app"


def _run_probe(
    cwd: pathlib.Path, code: str = _PROBE
) -> "subprocess.CompletedProcess[str]":
    """Run ``code`` in an isolated interpreter with working directory ``cwd``.

    Isolated mode (``-I``) means, like the ``alembic`` console script, that
    the working directory is not placed on ``sys.path``; ``PYTHONPATH`` is
    removed from the environment as well so no parent-process path can rescue
    an import.
    """
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_issue653_freeform():
    # ------------------------------------------------------------------
    # AC-1: the checked-in config sets prepend_sys_path = . in [alembic]
    # ------------------------------------------------------------------
    parser = configparser.ConfigParser()
    read = parser.read(_ALEMBIC_INI, encoding="utf-8")
    assert read, f"could not read {_ALEMBIC_INI}"
    assert parser.has_section("alembic")
    assert parser.get("alembic", "prepend_sys_path") == "."

    # ------------------------------------------------------------------
    # AC-2: isolated interpreter + the real alembic.ini -> import app works
    # ------------------------------------------------------------------
    ok = _run_probe(_BACKEND)
    assert ok.returncode == 0, (
        "probe against backend/alembic.ini must exit 0, got "
        f"rc={ok.returncode}\nstderr:\n{ok.stderr}"
    )

    # ------------------------------------------------------------------
    # AC-2 (negative): the same probe against an alembic.ini *without*
    # prepend_sys_path must fail with ModuleNotFoundError: No module named
    # 'app'.  The probe is isolated from any app package installed in the
    # environment: a shadow at sys.path[0] masks it, and a simulated
    # installed app proves the mask is load-bearing (without it, the
    # installed app alone would satisfy `import app` and the probe would
    # wrongly exit 0).
    # ------------------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="issue653-") as tmp:
        tmp_path = pathlib.Path(tmp)
        stripped_dir = tmp_path / "stripped"  # negative probe's cwd
        shadow_dir = tmp_path / "shadow"  # installed-app mask
        installed_dir = tmp_path / "installed"  # simulated site-packages app
        for directory in (stripped_dir, shadow_dir, installed_dir):
            directory.mkdir()

        # Drop the prepend_sys_path line, keeping every other byte intact.
        ini_lines = _ALEMBIC_INI.read_text(encoding="utf-8").splitlines(keepends=True)
        stripped_lines = [
            line
            for line in ini_lines
            if not line.strip().lower().startswith("prepend_sys_path")
        ]
        assert len(stripped_lines) < len(
            ini_lines
        ), "prepend_sys_path line not found in backend/alembic.ini"
        (stripped_dir / "alembic.ini").write_text(
            "".join(stripped_lines), encoding="utf-8"
        )
        os.symlink(_BACKEND / "migrations", stripped_dir / "migrations")

        (shadow_dir / "app.py").write_text(_SHADOW_SOURCE, encoding="utf-8")
        (installed_dir / "app").mkdir()
        (installed_dir / "app" / "__init__.py").write_text(
            f"MARKER = '{_SIMULATED_MARKER}'\n", encoding="utf-8"
        )

        # Proof the isolation is load-bearing: with an installed app present
        # (simulated at the end of sys.path, like site-packages) and no
        # shadow, the unisolated probe imports it and exits 0.
        control = _run_probe(
            stripped_dir,
            code=(
                f"import sys; sys.path.append({str(installed_dir)!r}); "
                "import app; print(app.__file__)"
            ),
        )
        assert control.returncode == 0, (
            "simulated installed app must be importable, otherwise the "
            f"isolation is not load-bearing, got rc={control.returncode}\n"
            f"stderr:\n{control.stderr}"
        )

        # The isolated negative probe: the shadow masks any installed app,
        # so `import app` can only fail with the ModuleNotFoundError the
        # absence of prepend_sys_path must produce.
        bad = _run_probe(
            stripped_dir,
            code=(
                f"import sys; "
                f"sys.path.insert(0, {str(shadow_dir)!r}); "
                f"sys.path.append({str(installed_dir)!r}); " + _PROBE
            ),
        )

    assert bad.returncode != 0, (
        "probe against the stripped alembic.ini must fail, but it exited 0 "
        f"(import app was satisfied outside the repo)\nstdout:\n{bad.stdout}"
    )
    assert "ModuleNotFoundError: No module named 'app'" in bad.stderr, (
        "stripped-ini probe must fail with "
        f"ModuleNotFoundError: No module named 'app'\nstderr:\n{bad.stderr}"
    )
