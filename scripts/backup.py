"""Create a consistent SQLite snapshot and optionally archive Markdown sources.

Usage:
    python scripts/backup.py
    python scripts/backup.py --archive
"""

from __future__ import annotations

import argparse
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path.home() / "research-data"
DB_PATH = DATA_DIR / "app.db"
BACKUP_DIR = DATA_DIR / "backups"


def snapshot_db(stamp: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"app-{stamp}.db"
    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    return target


def archive_markdown(stamp: str) -> Path:
    target = BACKUP_DIR / f"markdown-{stamp}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder in ("notes", "ideas", "experiments", "drafts"):
            root = DATA_DIR / folder
            if not root.exists():
                continue
            for path in root.rglob("*.md"):
                archive.write(path, path.relative_to(DATA_DIR))
        bib = DATA_DIR / "drafts"
        if bib.exists():
            for path in bib.rglob("refs.bib"):
                archive.write(path, path.relative_to(DATA_DIR))
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", action="store_true", help="also zip Markdown sources")
    args = parser.parse_args()
    if not DB_PATH.exists():
        raise SystemExit(f"database not found: {DB_PATH}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    db = snapshot_db(stamp)
    check = sqlite3.connect(db)
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    print(f"database snapshot: {db} ({db.stat().st_size:,} bytes)")
    print(f"integrity_check: {integrity}")
    if args.archive:
        archive = archive_markdown(stamp)
        print(f"markdown archive: {archive} ({archive.stat().st_size:,} bytes)")
    # Keep the 14 most recent database snapshots.
    snapshots = sorted(BACKUP_DIR.glob("app-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snapshots[14:]:
        old.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
