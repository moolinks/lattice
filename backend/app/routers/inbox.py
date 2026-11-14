from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Inbox
from ..utils import now_iso

router = APIRouter(prefix="/inbox", tags=["inbox"])


class InboxCreate(BaseModel):
    content: str


@router.get("")
def list_inbox(
    processed: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
):
    statement = select(Inbox)
    if processed is not None:
        statement = statement.where(Inbox.processed == (1 if processed else 0))
    items = session.exec(statement.order_by(Inbox.created_at.desc()).limit(limit)).all()
    return {
        "items": [
            {
                "id": i.id,
                "content": i.content,
                "processed": bool(i.processed),
                "created_at": i.created_at,
            }
            for i in items
        ]
    }


@router.post("")
def create_inbox(payload: InboxCreate, session: Session = Depends(get_session)):
    content = payload.content.strip()
    if not content:
        raise HTTPException(400, "content is empty")
    item = Inbox(content=content, created_at=now_iso())
    session.add(item)
    session.commit()
    session.refresh(item)
    return {"id": item.id, "content": item.content, "created_at": item.created_at}


@router.patch("/{item_id}")
def update_inbox(
    item_id: int,
    processed: bool = Query(...),
    session: Session = Depends(get_session),
):
    item = session.get(Inbox, item_id)
    if not item:
        raise HTTPException(404, "inbox item not found")
    item.processed = 1 if processed else 0
    session.add(item)
    session.commit()
    return {"ok": True}


@router.delete("/{item_id}")
def delete_inbox(item_id: int, session: Session = Depends(get_session)):
    item = session.get(Inbox, item_id)
    if not item:
        raise HTTPException(404, "inbox item not found")
    session.delete(item)
    session.commit()
    return {"ok": True}
