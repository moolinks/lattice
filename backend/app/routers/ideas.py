from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from ..config import IDEAS_DIR
from ..db import get_session
from ..markdown import dump_markdown, parse_markdown
from ..models import Idea
from ..services.indexer import index_idea
from ..services.linker import sync_links
from ..services.serializers import idea_out
from ..utils import next_id, now_iso, write_text

router = APIRouter(prefix="/ideas", tags=["ideas"])

IDEA_STATUSES = {"seed", "exploring", "hypothesis", "validated", "parked"}


class IdeaCreate(BaseModel):
    title: str
    summary: str = ""
    body: str = ""
    status: str = "seed"
    priority: int = 0
    inspired_by: list[str] = []
    tags: list[str] = []
    derived_from: list[str] = []


class IdeaUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    inspired_by: Optional[list[str]] = None
    derived_from: Optional[list[str]] = None
    tags: Optional[list[str]] = None


def _meta_for(idea: Idea, extra: dict | None = None) -> dict:
    doc = parse_markdown(idea.path) if idea.path else None
    meta = dict(doc.meta) if doc else {}
    meta.update(
        {
            "id": idea.id,
            "title": idea.title,
            "status": idea.status,
            "priority": idea.priority,
            "updated": idea.updated_at,
        }
    )
    if extra:
        meta.update(extra)
    return meta


@router.get("")
def list_ideas(
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
):
    statement = select(Idea)
    if status and status != "all":
        statement = statement.where(Idea.status == status)
    ideas = session.exec(
        statement.order_by(Idea.priority.desc(), Idea.updated_at.desc()).limit(limit)
    ).all()
    counts = {
        row[0]: row[1]
        for row in session.execute(text("SELECT status, count(*) FROM idea GROUP BY status")).all()
    }
    return {"items": [idea_out(session, i) for i in ideas], "status_counts": counts}


@router.post("")
def create_idea(payload: IdeaCreate, session: Session = Depends(get_session)):
    if payload.status not in IDEA_STATUSES:
        raise HTTPException(400, "invalid status")
    idea_id = next_id(session, "I")
    timestamp = now_iso()
    path = IDEAS_DIR / f"{idea_id}.md"
    meta = {
        "id": idea_id,
        "title": payload.title,
        "status": payload.status,
        "priority": payload.priority,
        "inspired_by": payload.inspired_by,
        "derived_from": payload.derived_from,
        "tags": payload.tags,
        "created": timestamp,
        "updated": timestamp,
    }
    body = payload.body or f"""## 观察

{payload.summary or '（先记录你注意到的异常、缺口或可迁移机制。）'}

## 假设

如果……，那么在……条件下，……指标会提升，因为……。

## 最小验证

- 数据：
- 基线：
- 消融：
- 成功判据：

## 风险

- 尚未记录。
"""
    idea = Idea(
        id=idea_id,
        title=payload.title,
        status=payload.status,
        priority=payload.priority,
        summary=payload.summary,
        path=str(path),
        created_at=timestamp,
        updated_at=timestamp,
    )
    write_text(path, dump_markdown(meta, body))
    session.add(idea)
    session.commit()
    session.refresh(idea)
    index_idea(session, idea)
    sync_links(session, idea_id, meta, body)
    session.commit()
    return idea_out(session, idea, detail=True)


@router.get("/{idea_id}")
def get_idea(idea_id: str, session: Session = Depends(get_session)):
    idea = session.get(Idea, idea_id)
    if not idea:
        raise HTTPException(404, "idea not found")
    return idea_out(session, idea, detail=True)


@router.patch("/{idea_id}")
def update_idea(idea_id: str, payload: IdeaUpdate, session: Session = Depends(get_session)):
    idea = session.get(Idea, idea_id)
    if not idea:
        raise HTTPException(404, "idea not found")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in IDEA_STATUSES:
        raise HTTPException(400, "invalid status")
    for key in ("title", "summary", "status", "priority"):
        if key in data:
            setattr(idea, key, data[key])
    idea.updated_at = now_iso()
    doc = parse_markdown(idea.path) if idea.path else None
    meta = dict(doc.meta) if doc else {}
    body = data.get("body", doc.body if doc else "")
    for key in ("inspired_by", "derived_from", "tags"):
        if key in data:
            meta[key] = data[key]
    if "title" in data:
        meta["title"] = data["title"]
    if "status" in data:
        meta["status"] = data["status"]
    if "priority" in data:
        meta["priority"] = data["priority"]
    meta["id"] = idea.id
    meta["updated"] = idea.updated_at
    if not idea.path:
        idea.path = str(IDEAS_DIR / f"{idea.id}.md")
    write_text(idea.path, dump_markdown(meta, body))
    session.add(idea)
    session.commit()
    session.refresh(idea)
    index_idea(session, idea)
    sync_links(session, idea.id, meta, body)
    session.commit()
    return idea_out(session, idea, detail=True)


@router.delete("/{idea_id}")
def delete_idea(idea_id: str, session: Session = Depends(get_session)):
    idea = session.get(Idea, idea_id)
    if not idea:
        raise HTTPException(404, "idea not found")
    session.execute(text("DELETE FROM link WHERE src_id = :id OR dst_id = :id"), {"id": idea_id})
    session.execute(text("DELETE FROM search_fts WHERE entity_id = :id"), {"id": idea_id})
    session.delete(idea)
    session.commit()
    return {"ok": True}


@router.post("/{idea_id}/promote")
def promote_idea(idea_id: str, session: Session = Depends(get_session)):
    """Create a one-paragraph experiment stub from an idea."""
    idea = session.get(Idea, idea_id)
    if not idea:
        raise HTTPException(404, "idea not found")
    from ..models import Experiment

    experiment_id = next_id(session, "E")
    timestamp = now_iso()
    path = IDEAS_DIR.parent / "experiments" / experiment_id / "notes.md"
    meta = {
        "id": experiment_id,
        "title": f"验证：{idea.title}",
        "idea_id": idea.id,
        "status": "planned",
        "created": timestamp,
    }
    body = f"""## 假设

{idea.summary or idea.title}

## 实验设计

- 数据：
- 基线：
- 处理组：
- 评价指标：
- 成功判据：

## 运行记录

"""
    write_text(path, dump_markdown(meta, body))
    experiment = Experiment(
        id=experiment_id,
        idea_id=idea.id,
        title=f"验证：{idea.title}",
        hypothesis=idea.summary or idea.title,
        status="planned",
        path=str(path),
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    from ..services.indexer import index_experiment

    index_experiment(session, experiment)
    sync_links(session, experiment_id, meta, body)
    session.commit()
    return {"experiment_id": experiment_id}
