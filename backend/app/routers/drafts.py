from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from ..config import DRAFTS_DIR
from ..db import get_session
from ..markdown import dump_markdown, parse_markdown
from ..models import Draft
from ..services.export import export_draft, tools_status
from ..services.indexer import index_draft
from ..services.linker import sync_links
from ..services.serializers import draft_out
from ..utils import next_id, now_iso, write_text

router = APIRouter(prefix="/drafts", tags=["drafts"])

DRAFT_STATUSES = {"outline", "writing", "review", "done"}


class DraftCreate(BaseModel):
    title: str
    venue: str = ""
    status: str = "outline"


class DraftUpdate(BaseModel):
    title: Optional[str] = None
    venue: Optional[str] = None
    status: Optional[str] = None
    body: Optional[str] = None


@router.get("")
def list_drafts(session: Session = Depends(get_session)):
    drafts = session.exec(select(Draft).order_by(Draft.updated_at.desc())).all()
    return {
        "items": [draft_out(session, draft) for draft in drafts],
        "tools": tools_status(),
    }


@router.post("")
def create_draft(payload: DraftCreate, session: Session = Depends(get_session)):
    if payload.status not in DRAFT_STATUSES:
        raise HTTPException(400, "invalid status")
    draft_id = next_id(session, "D")
    timestamp = now_iso()
    folder = DRAFTS_DIR / draft_id
    path = folder / "main.md"
    meta = {
        "id": draft_id,
        "title": payload.title,
        "venue": payload.venue,
        "status": payload.status,
        "created": timestamp,
        "updated": timestamp,
    }
    body = f"""# {payload.title}

## 摘要

（研究问题、方法、主要发现，各一句。）

## 1. 引言

社交关系如何改变生成式推荐的用户意图建模？本文关注……

## 2. 相关工作

生成式推荐用语义 ID / 生成式检索替代传统召回；社交推荐引入用户关系图。[@]

## 3. 方法

### 3.1 问题定义

### 3.2 关系条件生成

## 4. 实验

{{{{run:E0001-R01/curve.png}}}}

## 5. 讨论

## 参考文献
"""
    write_text(path, dump_markdown(meta, body))
    draft = Draft(
        id=draft_id,
        title=payload.title,
        venue=payload.venue,
        status=payload.status,
        path=str(path),
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    index_draft(session, draft)
    sync_links(session, draft_id, meta, body)
    session.commit()
    return draft_out(session, draft, detail=True)


@router.get("/{draft_id}")
def get_draft(draft_id: str, session: Session = Depends(get_session)):
    draft = session.get(Draft, draft_id)
    if not draft:
        raise HTTPException(404, "draft not found")
    return draft_out(session, draft, detail=True)


@router.put("/{draft_id}")
def update_draft(draft_id: str, payload: DraftUpdate, session: Session = Depends(get_session)):
    draft = session.get(Draft, draft_id)
    if not draft:
        raise HTTPException(404, "draft not found")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in DRAFT_STATUSES:
        raise HTTPException(400, "invalid status")
    body = data.pop("body", None)
    for key, value in data.items():
        setattr(draft, key, value)
    draft.updated_at = now_iso()
    doc = parse_markdown(draft.path) if draft.path else None
    meta = dict(doc.meta) if doc else {}
    meta.update(
        {
            "id": draft.id,
            "title": draft.title,
            "venue": draft.venue,
            "status": draft.status,
            "updated": draft.updated_at,
        }
    )
    if draft.path:
        write_text(
            draft.path,
            dump_markdown(meta, body if body is not None else (doc.body if doc else "")),
        )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    index_draft(session, draft)
    sync_links(
        session,
        draft_id,
        meta,
        body if body is not None else (doc.body if doc else ""),
    )
    session.commit()
    return draft_out(session, draft, detail=True)


@router.post("/{draft_id}/export")
def export_post(
    draft_id: str,
    format: str = Query("pdf", pattern="^(pdf|html|tex|md)$"),
    session: Session = Depends(get_session),
):
    return export_get(draft_id, format, session)


@router.get("/{draft_id}/export")
def export_get(
    draft_id: str,
    format: str = Query("pdf", pattern="^(pdf|html|tex|md)$"),
    session: Session = Depends(get_session),
):
    try:
        path, actual = export_draft(session, draft_id, format)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    media = {
        "html": "text/html; charset=utf-8",
        "pdf": "application/pdf",
        "tex": "text/plain; charset=utf-8",
        "md": "text/markdown; charset=utf-8",
    }[actual]
    return FileResponse(path, media_type=media, filename=f"{draft_id}.{actual}")


@router.delete("/{draft_id}")
def delete_draft(draft_id: str, session: Session = Depends(get_session)):
    draft = session.get(Draft, draft_id)
    if not draft:
        raise HTTPException(404, "draft not found")
    session.execute(text("DELETE FROM link WHERE src_id = :id OR dst_id = :id"), {"id": draft_id})
    session.execute(text("DELETE FROM search_fts WHERE entity_id = :id"), {"id": draft_id})
    session.delete(draft)
    session.commit()
    return {"ok": True}
