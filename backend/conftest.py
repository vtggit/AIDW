"""AIDW backend test-suite conftest (root of the pytest run).

The issue's proof nodeids (``tests/<name>.spec.js::<test title>``) name
the repo's Playwright proof specs by spec-file path and test title.  The
corresponding proof files under ``backend/tests/`` are Python modules —
despite the ``.spec.js`` name, they prove the same-named Playwright spec
the way the ``test_issue*_freeform.py`` tests do, statically, against the
app sources — that expose::

    PROOF_TITLES  the pytest item title(s) the file proves
    run(title)    performs the verification for one title

``pytest_collect_file`` below turns each such file into pytest items so
the gate can run them in the same pytest invocation as the rest of the
suite::

    cd backend && python -m pytest tests/<name>.spec.js::<title>

Only files under this directory's ``tests/`` package are considered, so a
run from the repo root never tries to import the Playwright specs in
``app/tests/``.
"""

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent / "tests"


class _ProofSpecItem(pytest.Item):
    """One proving test: its proof module's ``run(title)``."""

    def __init__(self, title, module, **kwargs):
        super().__init__(name=title, **kwargs)
        self._proof_title = title
        self._proof_module = module

    def runtest(self):
        self._proof_module.run(self._proof_title)

    def repr_failure(self, excinfo):
        return "proof %r failed: %s" % (self._proof_title, excinfo.value)


class _ProofSpecFile(pytest.File):
    """Collector for one ``tests/*.spec.js`` proof module."""

    def collect(self):
        module = _load_proof_module(self.path)
        for title in getattr(module, "PROOF_TITLES", None) or ():
            yield _ProofSpecItem.from_parent(self, title=title, module=module)


def _load_proof_module(path):
    modname = "_aidw_proof_%s" % path.stem.replace(".", "_")
    if modname in sys.modules:
        return sys.modules[modname]
    loader = importlib.machinery.SourceFileLoader(modname, str(path))
    spec = importlib.util.spec_from_loader(modname, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


def pytest_collect_file(file_path, parent):
    if file_path.suffix == ".js" and file_path.name.endswith(".spec.js"):
        try:
            if file_path.parent.resolve() == _TESTS_DIR:
                return _ProofSpecFile.from_parent(parent, path=file_path)
        except OSError:
            pass
    return None
