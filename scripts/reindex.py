"""Rebuild the full-text index and all Markdown-derived links.

Usage (from the repository root):
    uv run --project backend python scripts/reindex.py
or:
    backend/.venv/Scripts/python.exe scripts/reindex.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("RESEARCH_DATA_DIR", str(Path.home() / "research-data"))

from app.config import DATA_DIR  # noqa: E402
from app.db import init_db, session_scope  # noqa: E402
from app.services.indexer import reindex_all  # noqa: E402


def main() -> None:
    init_db()
    with session_scope() as session:
        report = reindex_all(session)
    report["data_dir"] = str(DATA_DIR)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
