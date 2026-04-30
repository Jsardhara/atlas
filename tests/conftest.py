"""Pytest config — wire ``agents/`` and the repo root onto ``sys.path``.

* ``agents/`` is added so ``from shared.x import y`` mirrors the layout used
  inside the per-agent Docker images (``PYTHONPATH=/app``).
* The repo root is added so the API package (``api.main`` etc) is importable
  by FastAPI tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / "agents"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
