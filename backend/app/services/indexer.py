from __future__ import annotations

import html
import re
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, select

from ..config import (
    DRAFTS_DIR,
    EXPERIMENTS_DIR,
    IDEAS_DIR,
    NOTES_DIR,
    load_settings,
)
from ..markdown import parse_markdown
from ..models import Chunk, Draft, Experiment, Idea, Paper
from .linker import rebuild_all_links, sync_links


def upsert_index(
    session: Session,
    row_id: str,
    entity_id: str,
    type_: str,
    page: int | None,
    title: str,
    body: str,
) -> None:
    session.execute(text("DELETE FROM search_fts WHERE row_id = :row_id"), {"row_id": row_id})
    session.execute(
        text(
            "INSERT INTO search_fts(row_id, entity_id, type, page, title, body) "
            "VALUES (:row_id, :entity_id, :type, :page, :title, :body)"
        ),
        {
            "row_id": row_id,
            "entity_id": entity_id,
            "type": type_,
            "page": page or 0,
            "title": title or "",
            "body": body or "",
        },
    )


def delete_index(session: Session, row_id: str) -> None:
    session.execute(text("DELETE FROM search_fts WHERE row_id = :row_id"), {"row_id": row_id})


def _scrub_body(text_value: str) -> str:
    # FTS5 treats some punctuation as syntax; indexed text is safe, but avoid
    # gigantic whitespace runs and NUL bytes from malformed PDFs.
    return re.sub(r"\s+", " ", (text_value or "").replace("\x00", " ")).strip()


def index_paper(session: Session, paper: Paper) -> None:
    note = parse_markdown(paper.note_path) if paper.note_path else None
    note_body = _scrub_body(note.body if note else "")
    abstract = _scrub_body(paper.abstract or "")
    upsert_index(
        session,
        row_id=paper.id,
        entity_id=paper.id,
        type_="paper",
        page=None,
        title=paper.title,
        body=f"{abstract}\n\n{note_body}".strip(),
    )
    if note_body:
        upsert_index(
            session,
            row_id=f"note:{paper.id}",
            entity_id=paper.id,
            type_="note",
            page=None,
            title=f"笔记 · {paper.title}",
            body=note_body,
        )
    else:
        delete_index(session, f"note:{paper.id}")

    session.execute(
        text("DELETE FROM search_fts WHERE entity_id = :eid AND type = 'paper_chunk'"),
        {"eid": paper.id},
    )
    chunks = session.exec(select(Chunk).where(Chunk.paper_id == paper.id).order_by(Chunk.id)).all()
    for chunk in chunks:
        upsert_index(
            session,
            row_id=chunk.id,
            entity_id=paper.id,
            type_="paper_chunk",
            page=chunk.page,
            title="",
            body=_scrub_body(chunk.text),
        )


def index_idea(session: Session, idea: Idea) -> None:
    doc = parse_markdown(idea.path) if idea.path else None
    body = _scrub_body((idea.summary or "") + "\n\n" + (doc.body if doc else ""))
    upsert_index(
        session,
        row_id=f"idea:{idea.id}",
        entity_id=idea.id,
        type_="idea",
        page=None,
        title=idea.title,
        body=body,
    )
    if doc:
        sync_links(session, idea.id, doc.meta, doc.body)


def index_experiment(session: Session, experiment: Experiment) -> None:
    doc = parse_markdown(experiment.path) if experiment.path else None
    body = _scrub_body((experiment.hypothesis or "") + "\n\n" + (doc.body if doc else ""))
    upsert_index(
        session,
        row_id=f"experiment:{experiment.id}",
        entity_id=experiment.id,
        type_="experiment",
        page=None,
        title=experiment.title,
        body=body,
    )
    if doc:
        sync_links(session, experiment.id, doc.meta, doc.body)


def index_draft(session: Session, draft: Draft) -> None:
    doc = parse_markdown(draft.path) if draft.path else None
    body = _scrub_body(doc.body if doc else "")
    upsert_index(
        session,
        row_id=f"draft:{draft.id}",
        entity_id=draft.id,
        type_="draft",
        page=None,
        title=draft.title,
        body=body,
    )
    if doc:
        sync_links(session, draft.id, doc.meta, doc.body)


def reindex_path(session: Session, path: str | Path) -> str | None:
    p = Path(path)
    if not p.exists() or p.suffix.lower() != ".md":
        return None
    try:
        rel = p.resolve().relative_to(NOTES_DIR.parent.resolve())
    except ValueError:
        return None
    parts = rel.parts
    if parts[0] == "notes" and p.parent.name == "notes":
        paper = session.get(Paper, p.stem.upper())
        if paper:
            paper.note_path = str(p)
            index_paper(session, paper)
            return paper.id
    elif parts[0] == "ideas" and p.parent.name == "ideas":
        idea = session.get(Idea, p.stem.upper())
        if idea:
            idea.path = str(p)
            index_idea(session, idea)
            return idea.id
    elif parts[0] == "experiments" and len(parts) > 1 and p.name == "notes.md":
        experiment = session.get(Experiment, parts[1].upper())
        if experiment:
            experiment.path = str(p)
            index_experiment(session, experiment)
            return experiment.id
    elif parts[0] == "drafts" and len(parts) > 1 and p.name == "main.md":
        draft = session.get(Draft, parts[1].upper())
        if draft:
            draft.path = str(p)
            index_draft(session, draft)
            return draft.id
    return None


def reindex_all(session: Session) -> dict:
    session.execute(text("DELETE FROM search_fts"))
    papers = session.exec(select(Paper).order_by(Paper.id)).all()
    for paper in papers:
        if paper.note_path and not Path(paper.note_path).exists():
            fallback = NOTES_DIR / f"{paper.id}.md"
            paper.note_path = str(fallback) if fallback.exists() else paper.note_path
        index_paper(session, paper)
    ideas = session.exec(select(Idea).order_by(Idea.id)).all()
    for idea in ideas:
        index_idea(session, idea)
    experiments = session.exec(select(Experiment).order_by(Experiment.id)).all()
    for experiment in experiments:
        index_experiment(session, experiment)
    drafts = session.exec(select(Draft).order_by(Draft.id)).all()
    for draft in drafts:
        index_draft(session, draft)
    links = rebuild_all_links(session)
    missing = [
        str(p)
        for p in (NOTES_DIR, IDEAS_DIR, EXPERIMENTS_DIR, DRAFTS_DIR)
        if not p.exists()
    ]
    rows = session.execute(text("SELECT count(*) FROM search_fts")).scalar_one()
    return {
        "papers": len(papers),
        "ideas": len(ideas),
        "experiments": len(experiments),
        "drafts": len(drafts),
        "links": links,
        "fts_rows": rows,
        "missing_dirs": missing,
    }


def _escape_snippet(value: str) -> str:
    value = value or ""
    value = value.replace("<mark>", "\x00MARK\x00").replace("</mark>", "\x00ENDMARK\x00")
    value = html.escape(value)
    return value.replace("\x00MARK\x00", "<mark>").replace("\x00ENDMARK\x00", "</mark>")


def to_fts_query(q: str) -> str:
    terms = [t for t in re.split(r"\s+", q.strip()) if t]
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in terms)


def _resolve_entities(session: Session, rows: list[dict]) -> dict[str, dict]:
    resolved: dict[str, dict] = {}
    for row in rows:
        entity_id = row["entity_id"]
        if entity_id in resolved:
            # Prefer the row with the strongest rank; bm25 is ascending.
            if row["raw_score"] < resolved[entity_id]["raw_score"]:
                resolved[entity_id].update(row)
            continue
        resolved[entity_id] = dict(row)
    return resolved


def search(
    session: Session,
    q: str,
    type_filter: str | None = None,
    limit: int = 40,
) -> dict:
    q = (q or "").strip()
    if not q:
        return {"query": q, "items": [], "total": 0, "mode": "empty", "groups": []}

    settings = load_settings()
    w_title = float(settings.get("bm25_title_weight", 10.0))
    w_body = float(settings.get("bm25_body_weight", 1.0))
    type_clause = " AND f.type = :type" if type_filter else ""
    params: dict = {"limit": max(limit * 3, 60)}
    if type_filter:
        params["type"] = type_filter

    use_like = len(q) < 3
    if not use_like:
        params["q"] = to_fts_query(q)
        sql = f"""
            SELECT f.row_id, f.entity_id, f.type, f.page, f.title,
                   snippet(search_fts, 5, '<mark>', '</mark>', '…', 28) AS snippet,
                   bm25(search_fts, 0, 0, 0, 0, :w_title, :w_body) AS raw_score
            FROM search_fts f
            WHERE search_fts MATCH :q {type_clause}
            ORDER BY raw_score ASC
            LIMIT :limit
        """
        params.update({"w_title": w_title, "w_body": w_body})
        try:
            rows = [dict(r) for r in session.execute(text(sql), params).mappings().all()]
        except Exception:
            use_like = True

    if use_like:
        like = f"%{q}%"
        params = {"like": like, "limit": max(limit * 3, 60)}
        if type_filter:
            params["type"] = type_filter
        sql = f"""
            SELECT f.row_id, f.entity_id, f.type, f.page, f.title,
                   substr(f.body, 1, 220) AS body_excerpt, 0.0 AS raw_score
            FROM search_fts f
            WHERE (f.title LIKE :like OR f.body LIKE :like) {type_clause}
            LIMIT :limit
        """
        rows = [dict(r) for r in session.execute(text(sql), params).mappings().all()]

    deduped = _resolve_entities(session, rows)
    paper_titles: dict[str, str] = {}
    items: list[dict] = []
    for entity_id, row in deduped.items():
        raw_score = float(row.get("raw_score") or 0.0)
        item_type = row["type"]
        title = row.get("title") or ""
        subtitle = ""
        page = row.get("page") or None
        if page == 0:
            page = None
        snippet = row.get("snippet")
        if snippet is None:
            excerpt = row.get("body_excerpt") or ""
            snippet = _escape_snippet(excerpt)
        else:
            snippet = _escape_snippet(snippet)

        if item_type in ("paper", "paper_chunk", "note"):
            if entity_id not in paper_titles:
                p = session.get(Paper, entity_id)
                paper_titles[entity_id] = p.title if p else entity_id
                if p and item_type == "paper":
                    subtitle = " · ".join(
                        [str(x) for x in (p.year, p.venue) if x]
                    )
            if item_type != "paper" or not title or title == paper_titles[entity_id]:
                title = paper_titles[entity_id]
            if item_type == "paper_chunk":
                subtitle = f"全文命中 · 第 {page or '?'} 页"
            elif item_type == "note":
                subtitle = "阅读笔记"
            item_type_out = "paper"
            href = f"/papers/{entity_id}"
            match_type = item_type
        elif item_type == "idea":
            idea = session.get(Idea, entity_id)
            subtitle = f"思路 · {idea.status if idea else 'seed'}"
            href = "/ideas"
            item_type_out = "idea"
            match_type = "idea"
        elif item_type == "experiment":
            exp = session.get(Experiment, entity_id)
            subtitle = f"实验 · {exp.status if exp else 'planned'}"
            href = f"/experiments/{entity_id}"
            item_type_out = "experiment"
            match_type = "experiment"
        elif item_type == "draft":
            draft = session.get(Draft, entity_id)
            subtitle = f"草稿 · {draft.status if draft else 'writing'}"
            href = f"/drafts/{entity_id}"
            item_type_out = "draft"
            match_type = "draft"
        else:
            href = "/"
            item_type_out = item_type
            match_type = item_type

        items.append(
            {
                "entity_id": entity_id,
                "type": item_type_out,
                "match_type": match_type,
                "title": title,
                "subtitle": subtitle,
                "snippet": snippet,
                "page": page,
                "href": href,
                "score": round(raw_score, 4),
                "relevance": round(1 / (1 + abs(raw_score) * 0.08), 3),
            }
        )
    items.sort(key=lambda x: x["score"])
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(item["type"], []).append(item)
    return {
        "query": q,
        "items": items[:limit],
        "groups": [{"type": k, "items": v[:12]} for k, v in groups.items()],
        "total": len(items),
        "mode": "like" if use_like else "bm25",
    }
