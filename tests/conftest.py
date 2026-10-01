import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(ROOT / "models" / "paddlex"))
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


def soffice_path():
    for c in (os.environ.get("SOFFICE"), shutil.which("soffice"), shutil.which("libreoffice"),
              *[str(p) for p in Path.home().glob(".local/opt/libreoffice/opt/libreoffice*/program/soffice")]):
        if c and Path(c).exists():
            return c
    return None


@pytest.fixture(scope="session")
def soffice():
    p = soffice_path()
    if not p:
        pytest.skip("LibreOffice not installed")
    return p


@pytest.fixture(scope="session")
def synth_page():
    from img2docx.synthetic import make_page

    return make_page(7, "ar")
