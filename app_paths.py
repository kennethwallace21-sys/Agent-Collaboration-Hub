"""Resolve code and private runtime directories without machine-specific paths."""
from __future__ import annotations

import os
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent


def workspace_root() -> Path:
    """All participants must select the same workspace to share one board."""
    configured = os.environ.get("COLLAB_WORKSPACE")
    return Path(configured).expanduser().resolve() if configured else CODE_DIR
