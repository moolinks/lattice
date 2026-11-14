from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from ..config import (
    DRAFTS_DIR,
    EXPERIMENTS_DIR,
    IDEAS_DIR,
    NOTES_DIR,
    PAPERS_DIR,
)
from ..markdown import MarkdownDoc, parse_markdown
from ..models import Paper
from ..utils import now_iso

ID_RE = re.compile(r"\[\[((?:P|I|E|D)\d{4}(?:-R\d{2})?)\]\]")
RUN_RE = re.compile(r"\{\{run:([A-Za-z0-9-]+)(?:/[^}]+)?\}\}")
CITE_RE = re.compile(r"\[@([A-Za-z0-9_:\-]+)\]")
FRONT_MATTER_RELATIONS = {
    "inspired_by": "inspired_by",
    "derived_from": "derived_from",
    "related": "related",
    "extends": "extends",
    "challenges": "challenges",
    "uses": "uses",
}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in re.split(r"[,，]", str(value)) if part.strip()]


def extract_links(
    session: Session, meta: dict[str, Any], body: str, src_id: str | None = None
) -> set[tuple[str, str]]:
    links: set[tuple[str, str]] = set()
    for field, relation in FRONT_MATTER_RELATIONS.items():
        for dst in _as_list(meta.get(field)):
            if re.fullmatch(r"(?:P|I|E|D)\d{4}(?:-R\d{2})?", dst):
                links.add((dst, relation))
    for match in ID_RE.finditer(body):
        links.add((match.group(1), "related"))
    for match in RUN_RE.finditer(body):
        links.add((match.group(1), "uses"))
    for match in CITE_RE.finditer(body):
        bibkey = match.group(1)
        paper = session.execute(text("SELECT id FROM paper WHERE bibkey = :k"), {"k": bibkey}).first()
        if paper:
            links.add((paper[0], "cites"))
    return {(dst, rel) for dst, rel in links if dst != src_id}


def sync_links(
    session: Session,
    src_id: str,
    meta: dict[str, Any],
    body: str,
) -> int:
    session.execute(text("DELETE FROM link WHERE src_id = :src"), {"src": src_id})
    links = extract_links(session, meta, body, src_id)
    for dst, relation in sorted(links):
        session.execute(
            text(
                "INSERT OR IGNORE INTO link(src_id, dst_id, relation, created_at) "
                "VALUES (:src, :dst, :rel, :ts)"
            ),
            {"src": src_id, "dst": dst, "rel": relation, "ts": now_iso()},
        )
    return len(links)


def _doc_id_for_path(path: Path) -> tuple[str | None, str]:
    """Return (entity id, entity kind) for a markdown file in the data directory."""
    try:
        rel = path.resolve().relative_to(NOTES_DIR.parent.resolve())
    except ValueError:
        return None, "unknown"
    parts = rel.parts
    name = path.stem.upper()
    if parts[0] == "notes" and re.fullmatch(r"P\d{4}", name) and path.parent == NOTES_DIR:
        return name, "paper"
    if parts[0] == "ideas" and re.fullmatch(r"I\d{4}", name) and path.parent == IDEAS_DIR:
        return name, "idea"
    if (
        parts[0] == "experiments"
        and len(parts) >= 2
        and re.fullmatch(r"E\d{4}", parts[1])
        and path.name == "notes.md"
    ):
        return parts[1], "experiment"
    if (
        parts[0] == "drafts"
        and len(parts) >= 2
        and re.fullmatch(r"D\d{4}", parts[1])
        and path.name == "main.md"
    ):
        return parts[1], "draft"
    return None, "unknown"


def rebuild_all_links(session: Session) -> int:
    session.execute(text("DELETE FROM link"))
    roots = [NOTES_DIR, IDEAS_DIR, EXPERIMENTS_DIR, DRAFTS_DIR]
    count = 0
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            entity_id, kind = _doc_id_for_path(path)
            if not entity_id:
                continue
            doc = parse_markdown(path)
            meta = dict(doc.meta)
            meta.setdefault("id", entity_id)
            meta.setdefault("kind", kind)
            count += sync_links(session, entity_id, meta, doc.body)
    return count


def doc_for_path(path: Path) -> MarkdownDoc:
    return parse_markdown(path)


def candidate_paths() -> list[Path]:
    paths: list[Path] = []
    for root in (NOTES_DIR, IDEAS_DIR, EXPERIMENTS_DIR, DRAFTS_DIR):
        if root.exists():
            paths.extend(root.rglob("*.md"))
    return paths


def note_path_for(paper: Paper) -> Path | None:
    if not paper.note_path:
        return None
    path = Path(paper.note_path)
    return path if path.exists() else NOTES_DIR / f"{paper.id}.md"


def all_source_files() -> list[Path]:
    return candidate_paths()


__all__ = [
    "PAPERS_DIR",
    "all_source_files",
    "extract_links",
    "note_path_for",
    "rebuild_all_links",
    "sync_links",
]
