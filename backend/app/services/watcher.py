from __future__ import annotations

import logging
import threading
from pathlib import Path

from watchfiles import watch

from ..config import DRAFTS_DIR, EXPERIMENTS_DIR, IDEAS_DIR, NOTES_DIR
from ..db import session_scope
from .indexer import reindex_path

logger = logging.getLogger(__name__)


class MarkdownWatcher:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="markdown-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        roots = [p for p in (NOTES_DIR, IDEAS_DIR, EXPERIMENTS_DIR, DRAFTS_DIR) if p.exists()]
        if not roots:
            return
        try:
            for changes in watch(*roots, debounce=900, stop_event=self._stop):
                for _change, raw_path in changes:
                    path = Path(raw_path)
                    if path.suffix.lower() != ".md":
                        continue
                    try:
                        with session_scope() as session:
                            entity_id = reindex_path(session, path)
                        if entity_id:
                            logger.info("reindexed %s from %s", entity_id, path.name)
                    except Exception:
                        logger.exception("failed to reindex %s", path)
        except Exception:
            logger.exception("markdown watcher stopped unexpectedly")


watcher = MarkdownWatcher()
