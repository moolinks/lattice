from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from ..db import get_session
from ..services.indexer import search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search_endpoint(
    q: str = Query("", max_length=300),
    type: Optional[str] = Query(None, pattern="^(paper|note|idea|experiment|draft)$"),
    limit: int = Query(40, ge=1, le=100),
    session: Session = Depends(get_session),
):
    return search(session, q, type, limit)
