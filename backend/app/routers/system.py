from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from ..config import (
    DATA_DIR,
    DB_PATH,
    VERSION,
    load_settings,
    public_settings,
    save_settings,
)
from ..db import get_session
from ..models import (
    Draft,
    Experiment,
    FeedItem,
    Idea,
    Inbox,
    Paper,
    Run,
)
from ..services.export import tools_status
from ..services.feed import refresh_if_stale
from ..services.indexer import reindex_all
from ..services.serializers import draft_out, feed_out, idea_out, paper_brief, run_out
from ..utils import now_iso

router = APIRouter(tags=["system"])


class SettingsPatch(BaseModel):
    research_field: Optional[str] = None
    research_focus: Optional[str] = None
    research_questions: Optional[list[str]] = None
    arxiv_keywords: Optional[list[str]] = None
    arxiv_categories: Optional[list[str]] = None
    bm25_title_weight: Optional[float] = None
    bm25_body_weight: Optional[float] = None
    anthropic_model: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    daily_feed_enabled: Optional[bool] = None
    daily_feed_hour: Optional[int] = None
    theme: Optional[str] = None


@router.get("/health")
def health(session: Session = Depends(get_session)):
    checks = {}
    try:
        session.execute(text("SELECT 1")).scalar_one()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
    try:
        fts_rows = session.execute(text("SELECT count(*) FROM search_fts")).scalar_one()
        checks["fts5"] = "ok"
    except Exception:
        fts_rows = 0
        checks["fts5"] = "missing"
    checks["data_dir"] = str(DATA_DIR)
    checks["data_dir_exists"] = DATA_DIR.exists()
    checks["db_size_bytes"] = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    checks["fts_rows"] = int(fts_rows)
    checks["tools"] = tools_status()
    checks["version"] = VERSION
    checks["status"] = "ok" if checks["database"] == "ok" and checks["fts5"] == "ok" else "degraded"
    return checks


@router.get("/dashboard")
def dashboard(session: Session = Depends(get_session)):
    settings = load_settings()
    now = datetime.now().astimezone()
    counts = {
        "papers": session.execute(text("SELECT count(*) FROM paper")).scalar_one(),
        "unread": session.execute(
            text("SELECT count(*) FROM paper WHERE status = 'unread'")
        ).scalar_one(),
        "reading": session.execute(
            text("SELECT count(*) FROM paper WHERE status = 'reading'")
        ).scalar_one(),
        "ideas": session.execute(text("SELECT count(*) FROM idea")).scalar_one(),
        "hypotheses": session.execute(
            text("SELECT count(*) FROM idea WHERE status IN ('hypothesis','validated')")
        ).scalar_one(),
        "experiments": session.execute(text("SELECT count(*) FROM experiment")).scalar_one(),
        "running_experiments": session.execute(
            text("SELECT count(*) FROM experiment WHERE status = 'running'")
        ).scalar_one(),
        "runs": session.execute(text("SELECT count(*) FROM run")).scalar_one(),
        "drafts": session.execute(text("SELECT count(*) FROM draft")).scalar_one(),
        "citations": session.execute(text("SELECT count(*) FROM paper WHERE bibkey IS NOT NULL")).scalar_one(),
        "annotations": session.execute(text("SELECT count(*) FROM annotation")).scalar_one(),
    }
    recent_papers = session.exec(select(Paper).order_by(Paper.updated_at.desc()).limit(5)).all()
    recent_ideas = session.exec(select(Idea).order_by(Idea.updated_at.desc()).limit(5)).all()
    drafts = session.exec(select(Draft).order_by(Draft.updated_at.desc()).limit(3)).all()
    feed = session.exec(
        select(FeedItem)
        .where(FeedItem.status == "new")
        .order_by(FeedItem.score.desc())
        .limit(5)
    ).all()
    inbox = session.exec(
        select(Inbox).where(Inbox.processed == 0).order_by(Inbox.created_at.desc()).limit(5)
    ).all()
    runs = session.exec(select(Run).order_by(Run.started_at.desc()).limit(5)).all()
    active_experiments = session.exec(
        select(Experiment).where(Experiment.status == "running").limit(4)
    ).all()

    activity = []
    for days_ago in range(6, -1, -1):
        day = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        count = 0
        for table in ("paper", "idea", "experiment", "draft"):
            count += session.execute(
                text(f"SELECT count(*) FROM {table} WHERE substr(updated_at, 1, 10) = :day"),
                {"day": day},
            ).scalar_one()
        activity.append({"date": day, "count": count})

    idea_counts = {
        row[0]: row[1]
        for row in session.execute(text("SELECT status, count(*) FROM idea GROUP BY status")).all()
    }
    tags = [
        {"name": row[0], "count": row[1]}
        for row in session.execute(
            text(
                "SELECT t.name, count(et.entity_id) AS c FROM tag t "
                "JOIN entity_tag et ON et.tag_id = t.id "
                "GROUP BY t.name ORDER BY c DESC LIMIT 12"
            )
        ).all()
    ]
    return {
        "greeting": _greeting(now.hour),
        "today": now.strftime("%Y年%m月%d日"),
        "weekday": "一二三四五六日"[now.weekday()],
        "focus": {
            "field": settings.get("research_field"),
            "subfield": settings.get("research_focus"),
            "questions": settings.get("research_questions", []),
        },
        "counts": counts,
        "recent_papers": [paper_brief(session, p) for p in recent_papers],
        "recent_ideas": [idea_out(session, i) for i in recent_ideas],
        "drafts": [draft_out(session, d) for d in drafts],
        "feed": [feed_out(f) for f in feed],
        "inbox": [
            {"id": i.id, "content": i.content, "created_at": i.created_at} for i in inbox
        ],
        "runs": [_dashboard_run(session, r) for r in runs],
        "active_experiments": [
            {
                "id": e.id,
                "title": e.title,
                "status": e.status,
                "idea_id": e.idea_id,
                "run_count": session.execute(
                    text("SELECT count(*) FROM run WHERE experiment_id = :eid"), {"eid": e.id}
                ).scalar_one(),
            }
            for e in active_experiments
        ],
        "activity": activity,
        "idea_counts": idea_counts,
        "tags": tags,
        "tools": tools_status(),
        "generated_at": now_iso(),
    }


def _dashboard_run(session: Session, run: Run) -> dict:
    data = run_out(session, run)
    experiment = session.get(Experiment, run.experiment_id)
    data["experiment_title"] = experiment.title if experiment else run.experiment_id
    return data


def _greeting(hour: int) -> str:
    if hour < 5:
        return "夜深了"
    if hour < 11:
        return "早上好"
    if hour < 14:
        return "中午好"
    if hour < 18:
        return "下午好"
    return "晚上好"


@router.get("/settings")
def get_settings():
    return public_settings()


@router.patch("/settings")
def update_settings(payload: SettingsPatch):
    data = payload.model_dump(exclude_unset=True)
    api_key = data.pop("anthropic_api_key", None)
    if api_key is not None:
        data["anthropic_api_key"] = api_key.strip()
    if "bm25_title_weight" in data and data["bm25_title_weight"] <= 0:
        raise HTTPException(400, "bm25_title_weight must be positive")
    if "bm25_body_weight" in data and data["bm25_body_weight"] <= 0:
        raise HTTPException(400, "bm25_body_weight must be positive")
    save_settings(data)
    result = public_settings()
    result["saved"] = True
    return result


@router.post("/admin/reindex")
def reindex(session: Session = Depends(get_session)):
    report = reindex_all(session)
    session.commit()
    save_settings({"last_reindex": now_iso()})
    report["ok"] = True
    return report


@router.get("/admin/stats")
def stats(session: Session = Depends(get_session)):
    tables = [
        "paper",
        "annotation",
        "idea",
        "experiment",
        "run",
        "metric",
        "artifact",
        "draft",
        "link",
        "tag",
        "entity_tag",
        "inbox",
        "feed_item",
        "chunk",
        "summary_record",
        "import_job",
    ]
    counts = {}
    for table in tables:
        counts[table] = session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
    return {
        "counts": counts,
        "db_size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "data_dir": str(DATA_DIR),
        "settings": public_settings(),
        "tools": tools_status(),
        "last_reindex": load_settings().get("last_reindex"),
    }


@router.post("/admin/backup")
def backup_db():
    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"app-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    backups = sorted(backup_dir.glob("app-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[14:]:
        old.unlink(missing_ok=True)
    return {"ok": True, "path": str(target), "size": target.stat().st_size}


@router.get("/admin/backups")
def backups():
    backup_dir = DATA_DIR / "backups"
    if not backup_dir.exists():
        return {"items": []}
    items = []
    for path in sorted(
        backup_dir.glob("app-*.db"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        items.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "mtime": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(
                    timespec="seconds"
                ),
            }
        )
    return {"items": items}


@router.get("/admin/feed-status")
def feed_status(session: Session = Depends(get_session)):
    last = session.execute(text("SELECT max(fetched_at) FROM feed_item")).scalar_one()
    return {"last_fetched": last, "due": last is None}


@router.post("/admin/refresh-feed")
def refresh_feed_now(session: Session = Depends(get_session)):
    report = refresh_if_stale(session, hours=0)
    session.commit()
    return report or {"fetched": 0, "added": 0, "updated": 0}
