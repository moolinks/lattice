from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Draft, Experiment, Idea, Link, Paper
from ..services.serializers import entity_brief
from ..utils import now_iso

router = APIRouter(tags=["links"])


class LinkCreate(BaseModel):
    src_id: str
    dst_id: str
    relation: str = "related"


@router.get("/links")
def list_links(
    entity_id: Optional[str] = None,
    relation: Optional[str] = None,
    session: Session = Depends(get_session),
):
    statement = select(Link)
    if relation:
        statement = statement.where(Link.relation == relation)
    links = session.exec(statement.order_by(Link.created_at.desc())).all()
    if entity_id:
        links = [
            link
            for link in links
            if link.src_id == entity_id or link.dst_id == entity_id
        ]
    items = []
    for link in links[:500]:
        src = entity_brief(session, link.src_id)
        dst = entity_brief(session, link.dst_id)
        if not src or not dst:
            continue
        items.append(
            {
                "src_id": link.src_id,
                "dst_id": link.dst_id,
                "relation": link.relation,
                "src": src,
                "dst": dst,
                "created_at": link.created_at,
            }
        )
    return {"items": items, "total": len(items)}


@router.post("/links")
def create_link(payload: LinkCreate, session: Session = Depends(get_session)):
    if not entity_brief(session, payload.src_id) or not entity_brief(session, payload.dst_id):
        raise HTTPException(404, "source or target entity not found")
    if payload.src_id == payload.dst_id:
        raise HTTPException(400, "self-links are not allowed")
    existing = session.get(Link, (payload.src_id, payload.dst_id, payload.relation))
    if existing:
        return {"ok": True, "existed": True}
    session.add(
        Link(
            src_id=payload.src_id,
            dst_id=payload.dst_id,
            relation=payload.relation,
            created_at=now_iso(),
        )
    )
    session.commit()
    return {"ok": True, "existed": False}


@router.delete("/links")
def delete_link(
    src_id: str,
    dst_id: str,
    relation: str,
    session: Session = Depends(get_session),
):
    link = session.get(Link, (src_id, dst_id, relation))
    if not link:
        raise HTTPException(404, "link not found")
    session.delete(link)
    session.commit()
    return {"ok": True}


@router.get("/graph")
def graph(session: Session = Depends(get_session)):
    nodes = []
    for paper in session.exec(select(Paper)).all():
        nodes.append(
            {
                "id": paper.id,
                "type": "paper",
                "label": paper.title,
                "status": paper.status,
                "year": paper.year,
                "degree": 0,
            }
        )
    for idea in session.exec(select(Idea)).all():
        nodes.append(
            {
                "id": idea.id,
                "type": "idea",
                "label": idea.title,
                "status": idea.status,
                "degree": 0,
            }
        )
    for experiment in session.exec(select(Experiment)).all():
        nodes.append(
            {
                "id": experiment.id,
                "type": "experiment",
                "label": experiment.title,
                "status": experiment.status,
                "degree": 0,
            }
        )
    for draft in session.exec(select(Draft)).all():
        nodes.append(
            {
                "id": draft.id,
                "type": "draft",
                "label": draft.title,
                "status": draft.status,
                "degree": 0,
            }
        )
    node_map = {node["id"]: node for node in nodes}
    edges = []
    for link in session.exec(select(Link)).all():
        if link.src_id not in node_map or link.dst_id not in node_map:
            continue
        edges.append(
            {
                "source": link.src_id,
                "target": link.dst_id,
                "relation": link.relation,
            }
        )
        node_map[link.src_id]["degree"] += 1
        node_map[link.dst_id]["degree"] += 1
    counts: dict[str, int] = {}
    for node in nodes:
        counts[node["type"]] = counts.get(node["type"], 0) + 1
    return {"nodes": nodes, "edges": edges, "counts": counts}
