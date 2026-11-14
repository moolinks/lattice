from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, text
from sqlmodel import Session, select

from ..agents.paper_summarizer import PaperSummaryAgent, summary_history
from ..config import DATA_DIR
from ..db import get_session
from ..markdown import dump_markdown, parse_markdown
from ..models import Annotation, Chunk, Paper
from ..services.ai import ask_paper
from ..services.indexer import index_paper
from ..services.ingest import (
    enqueue_import,
    get_job,
    save_uploaded_pdf,
    set_paper_tags,
)
from ..services.linker import sync_links
from ..services.serializers import paper_brief, paper_detail
from ..utils import now_iso, write_text

router = APIRouter(prefix="/papers", tags=["papers"])

PAPER_STATUSES = {"unread", "reading", "read", "key", "archived"}


class ImportRequest(BaseModel):
    source: str
    kind: str = "auto"


class PaperPatch(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    rating: Optional[int] = None
    abstract: Optional[str] = None
    venue: Optional[str] = None
    year: Optional[int] = None
    tags: Optional[list[str]] = None


class NoteUpdate(BaseModel):
    body: str
    meta: Optional[dict] = None


class AnnotationCreate(BaseModel):
    page: Optional[int] = None
    quote: str = ""
    comment: str = ""
    color: str = "amber"
    rects: Optional[list] = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.get("")
def list_papers(
    status: Optional[str] = None,
    tag: Optional[str] = None,
    year: Optional[int] = None,
    q: Optional[str] = None,
    sort: str = "updated",
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    statement = select(Paper)
    if status and status != "all":
        statement = statement.where(Paper.status == status)
    if year:
        statement = statement.where(Paper.year == year)
    if q:
        like = f"%{q}%"
        statement = statement.where(
            or_(
                Paper.title.like(like),
                Paper.abstract.like(like),
                Paper.authors.like(like),
                Paper.venue.like(like),
            )
        )
    if tag:
        ids = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT et.entity_id FROM entity_tag et JOIN tag t ON t.id = et.tag_id "
                    "WHERE t.name = :name"
                ),
                {"name": tag},
            ).all()
        ]
        statement = statement.where(Paper.id.in_(ids))  # type: ignore[attr-defined]
    total = session.exec(select(func.count()).select_from(statement.subquery())).one()
    if sort == "year":
        statement = statement.order_by(Paper.year.desc().nullslast(), Paper.updated_at.desc())
    elif sort == "rating":
        statement = statement.order_by(Paper.rating.desc().nullslast(), Paper.updated_at.desc())
    elif sort == "title":
        statement = statement.order_by(Paper.title)
    else:
        statement = statement.order_by(Paper.updated_at.desc())
    papers = session.exec(statement.offset(offset).limit(limit)).all()
    counts = {
        row[0]: row[1]
        for row in session.execute(
            text("SELECT status, count(*) FROM paper GROUP BY status")
        ).all()
    }
    all_tags = [
        row[0]
        for row in session.execute(
            text("SELECT name FROM tag ORDER BY name")
        ).all()
    ]
    return {
        "items": [paper_brief(session, p) for p in papers],
        "total": total,
        "limit": limit,
        "offset": offset,
        "status_counts": counts,
        "tags": all_tags,
    }


@router.get("/imports")
def recent_imports(limit: int = Query(10, ge=1, le=50), session: Session = Depends(get_session)):
    from ..models import ImportJob

    jobs = session.exec(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(limit)).all()
    return {
        "items": [
            {
                "id": j.id,
                "status": j.status,
                "progress": j.progress,
                "message": j.message,
                "paper_id": j.paper_id,
                "created_at": j.created_at,
                "kind": j.kind,
            }
            for j in jobs
        ]
    }


@router.get("/{paper_id}")
def get_paper(paper_id: str, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "paper not found")
    return paper_detail(session, paper)


@router.patch("/{paper_id}")
def update_paper(paper_id: str, payload: PaperPatch, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "paper not found")
    data = payload.model_dump(exclude_unset=True)
    tags = data.pop("tags", None)
    if "status" in data and data["status"] not in PAPER_STATUSES:
        raise HTTPException(400, "invalid status")
    for key, value in data.items():
        setattr(paper, key, value)
    paper.updated_at = now_iso()
    session.add(paper)
    if tags is not None:
        set_paper_tags(session, paper_id, tags)
    session.commit()
    # Refresh FTS entity after metadata edits.
    session.refresh(paper)
    index_paper(session, paper)
    session.commit()
    return paper_detail(session, paper)


@router.delete("/{paper_id}")
def delete_paper(paper_id: str, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "paper not found")
    session.execute(
        text("DELETE FROM link WHERE src_id = :id OR dst_id = :id"),
        {"id": paper_id},
    )
    session.execute(
        text("DELETE FROM search_fts WHERE entity_id = :id"),
        {"id": paper_id},
    )
    for model, column in (
        (Chunk, Chunk.paper_id),
        (Annotation, Annotation.paper_id),
    ):
        session.execute(
            text(f"DELETE FROM {model.__tablename__} WHERE {column.key} = :id"),
            {"id": paper_id},
        )
    session.execute(
        text("DELETE FROM entity_tag WHERE entity_id = :id"), {"id": paper_id}
    )
    session.delete(paper)
    session.commit()
    return {"ok": True}


@router.get("/{paper_id}/pdf")
def get_pdf(paper_id: str, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper or not paper.pdf_path:
        raise HTTPException(404, "PDF not found")
    path = Path(paper.pdf_path).resolve()
    try:
        path.relative_to(DATA_DIR.resolve())
    except ValueError:
        raise HTTPException(403, "invalid pdf path") from None
    if not path.exists():
        raise HTTPException(404, "PDF file missing")
    return FileResponse(path, media_type="application/pdf", filename=f"{paper_id}.pdf")


@router.get("/{paper_id}/chunks")
def get_chunks(
    paper_id: str,
    page: Optional[int] = None,
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    statement = select(Chunk).where(Chunk.paper_id == paper_id)
    if page:
        statement = statement.where(Chunk.page == page)
    chunks = session.exec(statement.order_by(Chunk.id).limit(limit)).all()
    return {
        "items": [{"id": c.id, "page": c.page, "text": c.text} for c in chunks],
        "count": len(chunks),
    }


@router.put("/{paper_id}/note")
def save_note(paper_id: str, payload: NoteUpdate, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper or not paper.note_path:
        raise HTTPException(404, "paper note not found")
    doc = parse_markdown(paper.note_path)
    meta = dict(doc.meta)
    if payload.meta:
        meta.update(payload.meta)
    meta.setdefault("id", paper_id)
    meta.setdefault("title", paper.title)
    meta["updated"] = now_iso()
    write_text(paper.note_path, dump_markdown(meta, payload.body))
    paper.updated_at = now_iso()
    session.add(paper)
    session.commit()
    session.refresh(paper)
    index_paper(session, paper)
    sync_links(session, paper_id, meta, payload.body)
    session.commit()
    return {"ok": True, "updated_at": paper.updated_at, "body": payload.body, "meta": meta}


@router.post("/{paper_id}/annotations")
def create_annotation(
    paper_id: str, payload: AnnotationCreate, session: Session = Depends(get_session)
):
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "paper not found")
    annotation = Annotation(
        paper_id=paper_id,
        page=payload.page,
        quote=payload.quote,
        comment=payload.comment,
        color=payload.color,
        rects=json.dumps(payload.rects or [], ensure_ascii=False),
        created_at=now_iso(),
    )
    session.add(annotation)
    paper.updated_at = now_iso()
    session.add(paper)
    session.commit()
    session.refresh(annotation)
    return {"id": annotation.id, "ok": True}


@router.delete("/{paper_id}/annotations/{annotation_id}")
def delete_annotation(
    paper_id: str, annotation_id: int, session: Session = Depends(get_session)
):
    annotation = session.get(Annotation, annotation_id)
    if not annotation or annotation.paper_id != paper_id:
        raise HTTPException(404, "annotation not found")
    session.delete(annotation)
    session.commit()
    return {"ok": True}


@router.post("/{paper_id}/ask")
def ask(paper_id: str, payload: AskRequest, session: Session = Depends(get_session)):
    try:
        return ask_paper(session, paper_id, payload.question)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{paper_id}/summarize")
def summarize(paper_id: str, session: Session = Depends(get_session)):
    try:
        result = PaperSummaryAgent().summarize(session, paper_id)
        session.commit()
        return result
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{paper_id}/summaries")
def get_summaries(
    paper_id: str,
    limit: int = Query(8, ge=1, le=50),
    session: Session = Depends(get_session),
):
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "paper not found")
    return {"items": summary_history(session, paper_id, limit=limit)}


@router.post("/import")
def import_paper(payload: ImportRequest, session: Session = Depends(get_session)):
    source = payload.source.strip()
    if not source:
        raise HTTPException(400, "source is empty")
    job_id = enqueue_import(source, payload.kind)
    return {"job_id": job_id, "status": "queued"}


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...), session: Session = Depends(get_session)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "only PDF files are accepted")
    data = await file.read()
    if len(data) > 80 * 1024 * 1024:
        raise HTTPException(413, "PDF too large (max 80 MB)")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "invalid PDF file")
    path = save_uploaded_pdf(data, file.filename)
    job_id = enqueue_import(str(path), "pdf")
    return {"job_id": job_id, "status": "queued"}


@router.get("/imports/{job_id}")
def import_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "import job not found")
    return job
