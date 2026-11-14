from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from ..agents.paper_summarizer import latest_summary
from ..markdown import parse_markdown
from ..models import (
    Annotation,
    Artifact,
    Draft,
    Experiment,
    Idea,
    Paper,
    Run,
)
from ..utils import clip, loads


def _plain_markdown(text_value: str) -> str:
    text_value = re.sub(r"```[\s\S]*?```", " ", text_value or "")
    text_value = re.sub(r"^---[\s\S]*?---", " ", text_value, flags=re.M)
    text_value = re.sub(r"^#{1,6}\s*", "", text_value, flags=re.M)
    text_value = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text_value)
    text_value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text_value)
    text_value = re.sub(r"[*_`>~]", "", text_value)
    return " ".join(text_value.split())


def paper_tags(session: Session, paper_id: str) -> list[str]:
    rows = session.execute(
        text(
            "SELECT t.name FROM tag t JOIN entity_tag et ON et.tag_id = t.id "
            "WHERE et.entity_id = :eid ORDER BY t.name"
        ),
        {"eid": paper_id},
    ).all()
    return [r[0] for r in rows]


def annotation_count(session: Session, paper_id: str) -> int:
    return int(
        session.execute(
            text("SELECT count(*) FROM annotation WHERE paper_id = :eid"), {"eid": paper_id}
        ).scalar_one()
    )


def paper_brief(session: Session, paper: Paper) -> dict[str, Any]:
    note_body = ""
    if paper.note_path:
        note_body = parse_markdown(paper.note_path).body
    why_match = re.search(r"##\s*为什么读这篇\s*\n(.*?)(?=\n##\s|\Z)", note_body, re.S)
    excerpt_source = why_match.group(1) if why_match else re.sub(r"^#.+$", "", note_body, flags=re.M)
    excerpt_source = re.sub(r"^(?:>.*|\*\*.*|\s*)$", "", excerpt_source, flags=re.M)
    excerpt_source = re.sub(r"[*_`#>\[\]]", "", excerpt_source)
    excerpt_source = " ".join(excerpt_source.split())
    return {
        "id": paper.id,
        "title": paper.title,
        "authors": loads(paper.authors, []),
        "year": paper.year,
        "venue": paper.venue,
        "abstract": paper.abstract,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "url": paper.url,
        "bibkey": paper.bibkey,
        "status": paper.status,
        "rating": paper.rating,
        "ai_summary": paper.ai_summary,
        "note_path": paper.note_path,
        "created_at": paper.created_at,
        "updated_at": paper.updated_at,
        "has_pdf": bool(paper.pdf_path),
        "pdf_url": f"/api/papers/{paper.id}/pdf" if paper.pdf_path else None,
        "tags": paper_tags(session, paper.id),
        "annotation_count": annotation_count(session, paper.id),
        "note_excerpt": clip(excerpt_source, 170),
    }


def paper_detail(session: Session, paper: Paper) -> dict[str, Any]:
    data = paper_brief(session, paper)
    note = parse_markdown(paper.note_path) if paper.note_path else None
    chunks_count = session.execute(
        text("SELECT count(*) FROM chunk WHERE paper_id = :eid"), {"eid": paper.id}
    ).scalar_one()
    annotations = session.exec(
        select(Annotation).where(Annotation.paper_id == paper.id).order_by(Annotation.page, Annotation.id)
    ).all()
    data.update(
        {
            "note": {
                "body": note.body if note else "",
                "meta": note.meta if note else {},
            },
            "chunks_count": int(chunks_count),
            "annotations": [
                {
                    "id": a.id,
                    "page": a.page,
                    "quote": a.quote,
                    "comment": a.comment,
                    "color": a.color,
                    "created_at": a.created_at,
                }
                for a in annotations
            ],
            "latest_summary": latest_summary(session, paper.id),
            "related": related_entities(session, paper.id),
        }
    )
    return data


def entity_brief(session: Session, entity_id: str) -> dict[str, Any] | None:
    paper = session.get(Paper, entity_id)
    if paper:
        return {"id": paper.id, "type": "paper", "title": paper.title, "status": paper.status}
    idea = session.get(Idea, entity_id)
    if idea:
        return {"id": idea.id, "type": "idea", "title": idea.title, "status": idea.status}
    experiment = session.get(Experiment, entity_id)
    if experiment:
        return {
            "id": experiment.id,
            "type": "experiment",
            "title": experiment.title,
            "status": experiment.status,
        }
    draft = session.get(Draft, entity_id)
    if draft:
        return {"id": draft.id, "type": "draft", "title": draft.title, "status": draft.status}
    run = session.get(Run, entity_id)
    if run:
        return {"id": run.id, "type": "run", "title": run.id, "status": run.status}
    return None


def related_entities(session: Session, entity_id: str) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            "SELECT src_id, dst_id, relation FROM link "
            "WHERE src_id = :eid OR dst_id = :eid ORDER BY created_at"
        ),
        {"eid": entity_id},
    ).all()
    result = []
    seen = set()
    for src, dst, relation in rows:
        other = dst if src == entity_id else src
        key = (other, relation)
        if key in seen:
            continue
        seen.add(key)
        brief = entity_brief(session, other)
        if brief:
            brief["relation"] = relation
            brief["direction"] = "out" if src == entity_id else "in"
            result.append(brief)
    return result


def idea_out(session: Session, idea: Idea, detail: bool = False) -> dict[str, Any]:
    doc = parse_markdown(idea.path) if idea.path else None
    data = {
        "id": idea.id,
        "title": idea.title,
        "status": idea.status,
        "priority": idea.priority,
        "summary": idea.summary,
        "path": idea.path,
        "created_at": idea.created_at,
        "updated_at": idea.updated_at,
        "excerpt": clip(idea.summary or (doc.body if doc else ""), 200),
        "tags": doc.meta.get("tags", []) if doc else [],
        "link_count": session.execute(
            text("SELECT count(*) FROM link WHERE src_id = :eid OR dst_id = :eid"),
            {"eid": idea.id},
        ).scalar_one(),
    }
    if detail:
        data["body"] = doc.body if doc else ""
        data["meta"] = doc.meta if doc else {}
        data["related"] = related_entities(session, idea.id)
    return data


def run_out(session: Session, run: Run, detail: bool = False) -> dict[str, Any]:
    data = {
        "id": run.id,
        "experiment_id": run.experiment_id,
        "status": run.status,
        "params": loads(run.params, {}),
        "summary": loads(run.summary, {}),
        "command": run.command,
        "git_commit": run.git_commit,
        "git_dirty": bool(run.git_dirty),
        "seed": run.seed,
        "host": run.host,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "artifacts": [
            {"id": a.id, "kind": a.kind, "path": a.path, "name": a.path.split("/")[-1]}
            for a in session.exec(select(Artifact).where(Artifact.run_id == run.id)).all()
        ],
    }
    metric_keys = session.execute(
        text("SELECT DISTINCT key FROM metric WHERE run_id = :rid ORDER BY key"),
        {"rid": run.id},
    ).all()
    data["metric_keys"] = [r[0] for r in metric_keys]
    if detail:
        data["metrics"] = {}
        for key in data["metric_keys"]:
            rows = session.execute(
                text(
                    "SELECT step, value FROM metric WHERE run_id = :rid AND key = :key "
                    "ORDER BY step"
                ),
                {"rid": run.id, "key": key},
            ).all()
            data["metrics"][key] = [{"step": s, "value": v} for s, v in rows]
    return data


def experiment_out(session: Session, experiment: Experiment, detail: bool = False) -> dict[str, Any]:
    doc = parse_markdown(experiment.path) if experiment.path else None
    runs = session.exec(
        select(Run).where(Run.experiment_id == experiment.id).order_by(Run.started_at.desc())
    ).all()
    data = {
        "id": experiment.id,
        "idea_id": experiment.idea_id,
        "title": experiment.title,
        "hypothesis": experiment.hypothesis,
        "status": experiment.status,
        "verdict": experiment.verdict,
        "path": experiment.path,
        "created_at": experiment.created_at,
        "updated_at": experiment.updated_at,
        "run_count": len(runs),
        "latest_run": run_out(session, runs[0]) if runs else None,
        "runs": [run_out(session, r, detail=detail) for r in runs],
        "excerpt": clip(experiment.hypothesis or (doc.body if doc else ""), 200),
    }
    if detail:
        data["body"] = doc.body if doc else ""
        data["meta"] = doc.meta if doc else {}
        data["related"] = related_entities(session, experiment.id)
    return data


def word_count(text_value: str) -> int:
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text_value))
    english = len(re.findall(r"[A-Za-z0-9]+", text_value))
    return chinese + english


def draft_out(session: Session, draft: Draft, detail: bool = False) -> dict[str, Any]:
    doc = parse_markdown(draft.path) if draft.path else None
    body = doc.body if doc else ""
    data = {
        "id": draft.id,
        "title": draft.title,
        "venue": draft.venue,
        "status": draft.status,
        "path": draft.path,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "word_count": word_count(body),
        "excerpt": clip(_plain_markdown(body), 240),
        "citation_count": len(re.findall(r"\[@[A-Za-z0-9_:\-]+\]", body)),
        "related": related_entities(session, draft.id),
    }
    if detail:
        data["body"] = body
        data["meta"] = doc.meta if doc else {}
    return data


def feed_out(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "arxiv_id": item.arxiv_id,
        "title": item.title,
        "authors": loads(item.authors, []),
        "abstract": item.abstract,
        "published": item.published,
        "score": item.score,
        "status": item.status,
        "fetched_at": item.fetched_at,
        "arxiv_url": f"https://arxiv.org/abs/{item.arxiv_id}",
    }
