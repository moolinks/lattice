from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlmodel import Session, select

from ..db import get_session
from ..models import FeedItem, Paper
from ..services.feed import refresh_feed
from ..services.ingest import enqueue_import
from ..services.serializers import feed_out
from ..utils import now_iso

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("")
def list_feed(
    status: str = "new",
    limit: int = Query(60, ge=1, le=200),
    session: Session = Depends(get_session),
):
    statement = select(FeedItem)
    if status != "all":
        statement = statement.where(FeedItem.status == status)
    items = session.exec(statement.order_by(FeedItem.score.desc()).limit(limit)).all()
    counts = {
        row[0]: row[1]
        for row in session.execute(
            text("SELECT status, count(*) FROM feed_item GROUP BY status")
        ).all()
    }
    last = session.execute(text("SELECT max(fetched_at) FROM feed_item")).scalar_one()
    return {
        "items": [feed_out(item) for item in items],
        "counts": counts,
        "last_fetched": last,
    }


@router.post("/refresh")
def refresh(
    limit: int = Query(40, ge=5, le=100),
    session: Session = Depends(get_session),
):
    try:
        result = refresh_feed(session, limit)
        session.commit()
        return result
    except Exception as exc:
        raise HTTPException(502, f"arXiv 抓取失败：{type(exc).__name__}: {exc}") from exc


@router.post("/{item_id}/accept")
def accept(item_id: int, session: Session = Depends(get_session)):
    item = session.get(FeedItem, item_id)
    if not item:
        raise HTTPException(404, "feed item not found")
    existing = session.exec(select(Paper).where(Paper.arxiv_id == item.arxiv_id)).first()
    item.status = "accepted"
    item.fetched_at = now_iso()
    session.add(item)
    session.commit()
    if existing:
        return {"paper_id": existing.id, "status": "already-imported"}
    job_id = enqueue_import(item.arxiv_id, "arxiv")
    return {"job_id": job_id, "status": "importing", "arxiv_id": item.arxiv_id}


@router.post("/{item_id}/ignore")
def ignore(item_id: int, session: Session = Depends(get_session)):
    item = session.get(FeedItem, item_id)
    if not item:
        raise HTTPException(404, "feed item not found")
    item.status = "ignored"
    session.add(item)
    session.commit()
    return {"ok": True}


@router.post("/{item_id}/reset")
def reset(item_id: int, session: Session = Depends(get_session)):
    item = session.get(FeedItem, item_id)
    if not item:
        raise HTTPException(404, "feed item not found")
    item.status = "new"
    session.add(item)
    session.commit()
    return {"ok": True}
