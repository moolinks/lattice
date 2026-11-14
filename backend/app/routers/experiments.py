from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from ..config import DATA_DIR, EXPERIMENTS_DIR
from ..db import get_session
from ..markdown import dump_markdown, parse_markdown
from ..models import Artifact, Experiment, Metric, Run
from ..services.indexer import index_experiment
from ..services.linker import sync_links
from ..services.serializers import experiment_out, run_out
from ..utils import dumps, loads, next_id, now_iso, write_text

router = APIRouter(prefix="/experiments", tags=["experiments"])
runs_router = APIRouter(prefix="/runs", tags=["runs"])

EXPERIMENT_STATUSES = {"planned", "running", "done", "blocked", "archived"}


class ExperimentCreate(BaseModel):
    title: str
    idea_id: Optional[str] = None
    hypothesis: str = ""
    body: str = ""
    status: str = "planned"


class ExperimentUpdate(BaseModel):
    title: Optional[str] = None
    hypothesis: Optional[str] = None
    status: Optional[str] = None
    verdict: Optional[str] = None
    body: Optional[str] = None
    idea_id: Optional[str] = None


class RunCreate(BaseModel):
    experiment_id: str
    params: dict[str, Any] = {}
    command: Optional[str] = None
    git_commit: Optional[str] = None
    git_dirty: bool = False
    seed: Optional[int] = None
    host: Optional[str] = None
    log_path: Optional[str] = None


class MetricPoint(BaseModel):
    key: str
    step: int = 0
    value: float
    ts: Optional[str] = None


class MetricBatch(BaseModel):
    metrics: list[MetricPoint]


class RunFinish(BaseModel):
    summary: dict[str, Any] = {}
    status: str = "done"


class ArtifactCreate(BaseModel):
    kind: str = "figure"
    path: str


def _experiment_meta(experiment: Experiment, body: str) -> dict:
    doc = parse_markdown(experiment.path) if experiment.path else None
    meta = dict(doc.meta) if doc else {}
    meta.update(
        {
            "id": experiment.id,
            "title": experiment.title,
            "status": experiment.status,
            "idea_id": experiment.idea_id,
            "updated": experiment.updated_at,
        }
    )
    return meta


@router.get("")
def list_experiments(
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
):
    statement = select(Experiment)
    if status and status != "all":
        statement = statement.where(Experiment.status == status)
    experiments = session.exec(
        statement.order_by(Experiment.updated_at.desc()).limit(limit)
    ).all()
    counts = {
        row[0]: row[1]
        for row in session.execute(
            text("SELECT status, count(*) FROM experiment GROUP BY status")
        ).all()
    }
    return {
        "items": [experiment_out(session, e) for e in experiments],
        "status_counts": counts,
    }


@router.post("")
def create_experiment(payload: ExperimentCreate, session: Session = Depends(get_session)):
    if payload.status not in EXPERIMENT_STATUSES:
        raise HTTPException(400, "invalid status")
    experiment_id = next_id(session, "E")
    timestamp = now_iso()
    folder = EXPERIMENTS_DIR / experiment_id
    path = folder / "notes.md"
    meta = {
        "id": experiment_id,
        "title": payload.title,
        "status": payload.status,
        "idea_id": payload.idea_id,
        "created": timestamp,
        "updated": timestamp,
    }
    body = payload.body or f"""## 假设

{payload.hypothesis or '（写下可证伪的假设。）'}

## 实验设计

- 数据：
- 基线：
- 处理组：
- 指标：
- 成功判据：

## 结果

## 结论与下一步

"""
    write_text(path, dump_markdown(meta, body))
    experiment = Experiment(
        id=experiment_id,
        idea_id=payload.idea_id,
        title=payload.title,
        hypothesis=payload.hypothesis,
        status=payload.status,
        path=str(path),
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    index_experiment(session, experiment)
    sync_links(session, experiment_id, meta, body)
    session.commit()
    return experiment_out(session, experiment, detail=True)


@router.get("/{experiment_id}")
def get_experiment(experiment_id: str, session: Session = Depends(get_session)):
    experiment = session.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(404, "experiment not found")
    return experiment_out(session, experiment, detail=True)


@router.patch("/{experiment_id}")
def update_experiment(
    experiment_id: str, payload: ExperimentUpdate, session: Session = Depends(get_session)
):
    experiment = session.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(404, "experiment not found")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in EXPERIMENT_STATUSES:
        raise HTTPException(400, "invalid status")
    body = data.pop("body", None)
    for key, value in data.items():
        setattr(experiment, key, value)
    experiment.updated_at = now_iso()
    doc = parse_markdown(experiment.path) if experiment.path else None
    meta = dict(doc.meta) if doc else {}
    meta.update(
        {
            "id": experiment.id,
            "title": experiment.title,
            "status": experiment.status,
            "idea_id": experiment.idea_id,
            "updated": experiment.updated_at,
        }
    )
    if experiment.path:
        write_text(
            experiment.path,
            dump_markdown(meta, body if body is not None else (doc.body if doc else "")),
        )
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    index_experiment(session, experiment)
    sync_links(
        session,
        experiment_id,
        meta,
        body if body is not None else (doc.body if doc else ""),
    )
    session.commit()
    return experiment_out(session, experiment, detail=True)


@router.delete("/{experiment_id}")
def delete_experiment(experiment_id: str, session: Session = Depends(get_session)):
    experiment = session.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(404, "experiment not found")
    runs = session.exec(select(Run).where(Run.experiment_id == experiment_id)).all()
    for run in runs:
        session.execute(text("DELETE FROM metric WHERE run_id = :rid"), {"rid": run.id})
        session.execute(text("DELETE FROM artifact WHERE run_id = :rid"), {"rid": run.id})
        session.delete(run)
    session.execute(
        text("DELETE FROM link WHERE src_id = :id OR dst_id = :id"), {"id": experiment_id}
    )
    session.execute(
        text("DELETE FROM search_fts WHERE entity_id = :id"), {"id": experiment_id}
    )
    session.delete(experiment)
    session.commit()
    return {"ok": True}


@router.get("/{experiment_id}/compare")
def compare_runs(
    experiment_id: str,
    runs: str = Query(..., description="comma separated run ids"),
    session: Session = Depends(get_session),
):
    experiment = session.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(404, "experiment not found")
    run_ids = [r.strip() for r in runs.split(",") if r.strip()]
    selected = [session.get(Run, run_id) for run_id in run_ids]
    selected = [r for r in selected if r and r.experiment_id == experiment_id]
    if not selected:
        raise HTTPException(400, "no valid runs")
    series: dict[str, Any] = {}
    all_keys: set[str] = set()
    for run in selected:
        rows = session.execute(
            text("SELECT key, step, value FROM metric WHERE run_id = :rid ORDER BY key, step"),
            {"rid": run.id},
        ).all()
        data: dict[str, list[dict]] = {}
        for key, step, value in rows:
            data.setdefault(key, []).append({"step": step, "value": value})
            all_keys.add(key)
        series[run.id] = data
    param_maps = {run.id: loads(run.params, {}) for run in selected}
    keys = sorted({k for p in param_maps.values() for k in p})
    diff = {}
    for key in keys:
        values = {rid: p.get(key) for rid, p in param_maps.items()}
        if len({str(v) for v in values.values()}) > 1:
            diff[key] = values
    return {
        "experiment": {"id": experiment.id, "title": experiment.title},
        "runs": [
            {
                "id": run.id,
                "status": run.status,
                "params": param_maps[run.id],
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }
            for run in selected
        ],
        "metric_keys": sorted(all_keys),
        "series": series,
        "param_diff": diff,
    }


@router.post("/{experiment_id}/runs")
def create_run(
    experiment_id: str, payload: RunCreate, session: Session = Depends(get_session)
):
    experiment = session.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(404, "experiment not found")
    if payload.experiment_id != experiment_id:
        raise HTTPException(400, "experiment_id mismatch")
    existing = session.exec(select(Run).where(Run.experiment_id == experiment_id)).all()
    suffixes = []
    for run in existing:
        if "-R" in run.id:
            with contextlib.suppress(ValueError):
                suffixes.append(int(run.id.rsplit("-R", 1)[1]))
    run_id = f"{experiment_id}-R{max(suffixes, default=0) + 1:02d}"
    run = Run(
        id=run_id,
        experiment_id=experiment_id,
        status="running",
        params=dumps(payload.params),
        command=payload.command,
        git_commit=payload.git_commit,
        git_dirty=1 if payload.git_dirty else 0,
        seed=payload.seed,
        host=payload.host,
        log_path=payload.log_path,
        started_at=now_iso(),
    )
    session.add(run)
    if experiment.status in ("planned", "blocked"):
        experiment.status = "running"
        experiment.updated_at = now_iso()
        session.add(experiment)
    session.commit()
    session.refresh(run)
    return run_out(session, run, detail=True)


@runs_router.post("")
def create_run_root(payload: RunCreate, session: Session = Depends(get_session)):
    return create_run(payload.experiment_id, payload, session)


@runs_router.get("/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run_out(session, run, detail=True)


@runs_router.post("/{run_id}/metrics")
def add_metrics(run_id: str, payload: MetricBatch, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if len(payload.metrics) > 5000:
        raise HTTPException(413, "too many metric points in one batch")
    timestamp = now_iso()
    for point in payload.metrics:
        session.add(
            Metric(
                run_id=run_id,
                key=point.key,
                step=point.step,
                value=point.value,
                ts=point.ts or timestamp,
            )
        )
    session.commit()
    return {"ok": True, "count": len(payload.metrics)}


@runs_router.post("/{run_id}/finish")
def finish_run(run_id: str, payload: RunFinish, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    run.status = payload.status
    run.summary = dumps(payload.summary)
    run.finished_at = now_iso()
    session.add(run)
    experiment = session.get(Experiment, run.experiment_id)
    if experiment:
        remaining = session.exec(
            select(Run).where(Run.experiment_id == experiment.id, Run.status == "running")
        ).all()
        if not remaining:
            experiment.status = "done"
            experiment.updated_at = now_iso()
            session.add(experiment)
    session.commit()
    return run_out(session, run, detail=True)


@runs_router.post("/{run_id}/artifacts")
def add_artifact(
    run_id: str, payload: ArtifactCreate, session: Session = Depends(get_session)
):
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    path = Path(payload.path)
    if not path.is_absolute():
        path = DATA_DIR / path
    if not path.exists():
        raise HTTPException(400, "artifact path does not exist")
    artifact = Artifact(
        run_id=run_id,
        kind=payload.kind,
        path=str(path),
        created_at=now_iso(),
    )
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    return {"id": artifact.id, "path": artifact.path}


@router.put("/{experiment_id}/note")
def save_experiment_note(
    experiment_id: str,
    payload: dict,
    session: Session = Depends(get_session),
):
    experiment = session.get(Experiment, experiment_id)
    if not experiment or not experiment.path:
        raise HTTPException(404, "experiment not found")
    body = payload.get("body", "")
    doc = parse_markdown(experiment.path)
    meta = dict(doc.meta)
    meta["updated"] = now_iso()
    write_text(experiment.path, dump_markdown(meta, body))
    experiment.updated_at = now_iso()
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    index_experiment(session, experiment)
    sync_links(session, experiment_id, meta, body)
    session.commit()
    return {"ok": True}


@router.get("/{experiment_id}/runs/{run_id}/artifacts/{artifact_id}")
def get_artifact_file(
    experiment_id: str,
    run_id: str,
    artifact_id: int,
    session: Session = Depends(get_session),
):
    from fastapi.responses import FileResponse

    run = session.get(Run, run_id)
    artifact = session.get(Artifact, artifact_id)
    if not run or run.experiment_id != experiment_id or not artifact or artifact.run_id != run_id:
        raise HTTPException(404, "artifact not found")
    path = Path(artifact.path).resolve()
    try:
        path.relative_to(DATA_DIR.resolve())
    except ValueError:
        raise HTTPException(403, "invalid artifact path") from None
    if not path.exists():
        raise HTTPException(404, "artifact file missing")
    return FileResponse(path)
