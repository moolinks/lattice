from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text
from sqlmodel import Session, select

from ..config import load_settings
from ..models import FeedItem, Paper
from ..utils import dumps, now_iso

ATOM = {"a": "http://www.w3.org/2005/Atom"}
ARXIV_ID = re.compile(r"abs/([^/]+?)(?:v\d+)?$")


def _parse_entries(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", ATOM):
        raw_id = entry.findtext("a:id", default="", namespaces=ATOM)
        match = re.search(r"abs/([^/]+?)(?:v\d+)?$", raw_id)
        if not match:
            continue
        arxiv_id = match.group(1)
        title = " ".join(entry.findtext("a:title", default="", namespaces=ATOM).split())
        abstract = " ".join(entry.findtext("a:summary", default="", namespaces=ATOM).split())
        authors = [
            " ".join(node.findtext("a:name", default="", namespaces=ATOM).split())
            for node in entry.findall("a:author", ATOM)
        ]
        published = entry.findtext("a:published", default="", namespaces=ATOM)
        items.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": [a for a in authors if a],
                "published": published[:10],
            }
        )
    return items


def _score(item: dict[str, Any], keywords: list[str]) -> float:
    haystack = f"{item['title']} {item['abstract']}".lower()
    score = 0.0
    for keyword in keywords:
        k = keyword.lower()
        if k in item["title"].lower():
            score += 3.2
        score += min(haystack.count(k), 4) * 0.8
    # Generative + social intersection gets an explicit nudge.
    if "generat" in haystack and ("social" in haystack or "graph" in haystack):
        score += 2.0
    if "recommend" in haystack:
        score += 0.8
    try:
        published = datetime.strptime(item["published"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        age = max((datetime.now(timezone.utc) - published).days, 0)
        score += max(0.0, 1.2 - age / 120)
    except Exception:
        pass
    return round(score, 3)


def build_query(settings: dict[str, Any]) -> str:
    keywords = settings.get("arxiv_keywords") or ["generative recommendation"]
    categories = settings.get("arxiv_categories") or ["cs.IR"]
    clauses = []
    for keyword in keywords[:6]:
        safe = keyword.replace('"', "")
        clauses.append(f'abs:"{safe}"')
    category_clause = " OR ".join(f"cat:{c}" for c in categories)
    return f"({category_clause}) AND ({' OR '.join(clauses)})"


def fetch_arxiv_feed(limit: int = 40) -> list[dict[str, Any]]:
    settings = load_settings()
    query = build_query(settings)
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max(1, min(limit, 100)),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    headers = {"User-Agent": "LatticeResearchHub/0.1 (local personal research tool)"}
    with httpx.Client(timeout=45, follow_redirects=True, headers=headers) as client:
        response = client.get("https://export.arxiv.org/api/query", params=params)
        response.raise_for_status()
    items = _parse_entries(response.text)
    keywords = settings.get("arxiv_keywords") or []
    for item in items:
        item["score"] = _score(item, keywords)
    items.sort(key=lambda x: x["score"], reverse=True)
    return items


def refresh_feed(session: Session, limit: int = 40) -> dict[str, Any]:
    fetched = fetch_arxiv_feed(limit)
    added = 0
    updated = 0
    for item in fetched:
        existing = session.exec(
            select(FeedItem).where(FeedItem.arxiv_id == item["arxiv_id"])
        ).first()
        if existing:
            existing.score = item["score"]
            existing.fetched_at = now_iso()
            updated += 1
        else:
            session.add(
                FeedItem(
                    arxiv_id=item["arxiv_id"],
                    title=item["title"],
                    authors=dumps(item["authors"]),
                    abstract=item["abstract"],
                    published=item["published"],
                    score=item["score"],
                    status="new",
                    fetched_at=now_iso(),
                )
            )
            added += 1
    return {"fetched": len(fetched), "added": added, "updated": updated}


def refresh_if_stale(session: Session, hours: int = 12) -> dict[str, Any] | None:
    last = session.execute(text("SELECT max(fetched_at) FROM feed_item")).scalar_one()
    if not last:
        return refresh_feed(session)
    try:
        last_dt = datetime.fromisoformat(last)
        age = datetime.now(timezone.utc) - last_dt
        if age.total_seconds() < hours * 3600:
            return None
    except Exception:
        pass
    time.sleep(1)
    return refresh_feed(session)


def accept_feed(session: Session, item_id: int) -> str:
    item = session.get(FeedItem, item_id)
    if not item:
        raise ValueError("feed item not found")
    existing = session.exec(select(Paper).where(Paper.arxiv_id == item.arxiv_id)).first()
    if existing:
        item.status = "accepted"
        return existing.id
    item.status = "accepted"
    return item.arxiv_id
