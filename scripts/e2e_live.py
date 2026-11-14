"""Live end-to-end test for every Lattice feature.

Run against an isolated instance so your real data is never touched:

    $env:RESEARCH_DATA_DIR = "...\\e2e-data"
    $env:RESEARCH_HUB_SCHEDULER = "0"
    uvicorn app.main:app --port 8765
    python scripts/e2e_live.py --base-url http://127.0.0.1:8765

This covers: health, settings, arXiv import/download, PDF serving, FTS5 search
(including the short-query fallback), summary agent + history, ask fallback,
notes, annotations, ideas, promote-to-experiment, runs, metrics, artifacts,
comparison, draft HTML/PDF export, links, graph, inbox, feed refresh/accept/
ignore, reindex, stats and backup.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import pymupdf as fitz  # noqa: E402

BASE = "http://127.0.0.1:8765"
ARXIV_ID = "1706.03762"  # Attention Is All You Need — stable and public
RESULTS: list[dict] = []
REPORT = ROOT / "docs" / "E2E_REPORT.md"


def api(method: str, path: str, payload=None, raw: bool = False):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE}/api{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
        if raw:
            return response, body
        return json.loads(body) if body else None


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    RESULTS.append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name} {detail}")
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def wait_job(job_id: str, timeout: float = 150) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = api("GET", f"/papers/imports/{job_id}")
        if job["status"] in {"complete", "failed"}:
            check(f"import job {job['status']}", job["status"] == "complete", job.get("message", ""))
            if job["status"] == "complete":
                return job
            break
        time.sleep(1)
    raise AssertionError(f"import job {job_id} did not finish")


def upload_pdf(path: Path):
    boundary = f"----lattice{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"{BASE}/api/papers/upload",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def synthetic_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 72), "A Synthetic Test Paper for Lattice", fontsize=20, fontname="helv")
    page.insert_text(
        (54, 110),
        "We address the problem of verifying a local research system end to end. "
        "The central challenge is to produce reproducible paper metadata, searchable "
        "chunks and page-level evidence without relying on a cloud service.",
        fontsize=10,
        fontname="helv",
    )
    page.insert_text(
        (54, 170),
        "Abstract: This synthetic document exercises import, search, summary and export.",
        fontsize=10,
        fontname="helv",
    )
    page2 = doc.new_page()
    page2.insert_text((54, 72), "2. Method", fontsize=16, fontname="helv")
    page2.insert_text(
        (54, 100),
        "We propose a deterministic evidence agent. The method selects claim-bearing "
        "sentences from page-aware chunks and records page numbers for every quote.",
        fontsize=10,
        fontname="helv",
    )
    page2.insert_text((54, 150), "3. Experiments", fontsize=16, fontname="helv")
    page2.insert_text(
        (54, 178),
        "In our evaluation, the local extractive summary achieves full evidence "
        "coverage on this fixture. Results show that every summary is persisted with "
        "a prompt version and page citations.",
        fontsize=10,
        fontname="helv",
    )
    doc.new_page().insert_text(
        (54, 90),
        "4. Limitations: This is a synthetic test fixture and does not report real "
        "research findings. Future work should add human evaluation.",
        fontsize=10,
        fontname="helv",
    )
    doc.save(path)
    doc.close()


def main() -> None:
    global BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE)
    parser.add_argument("--arxiv", default=ARXIV_ID)
    args = parser.parse_args()
    BASE = args.base_url.rstrip("/")
    started = time.time()

    health = api("GET", "/health")
    check("health", health["status"] == "ok" and health["fts5"] == "ok")
    check("toolchain", health["tools"]["pdf_export"] is True, "pandoc + tectonic available")

    settings = api("GET", "/settings")
    check("settings", bool(settings["data_dir"]))

    # ---------------------------------------------------------------- import
    job = api("POST", "/papers/import", {"source": args.arxiv, "kind": "arxiv"})
    imported = wait_job(job["job_id"])
    paper_id = imported["paper_id"]
    check("arxiv import", bool(paper_id), paper_id)

    paper = api("GET", f"/papers/{paper_id}")
    check("paper metadata", bool(paper["title"]) and bool(paper["pdf_url"]), "metadata ok")
    check("pdf chunks", paper["chunks_count"] > 0, f"{paper['chunks_count']} chunks")

    response, pdf_bytes = api("GET", f"/papers/{paper_id}/pdf", raw=True)
    check(
        "download PDF",
        pdf_bytes.startswith(b"%PDF") and len(pdf_bytes) > 50_000,
        f"{len(pdf_bytes):,} bytes",
    )
    check("PDF content-type", "application/pdf" in response.headers.get("Content-Type", ""))

    # ---------------------------------------------------------------- search
    listing = api("GET", "/papers")
    check("paper list", listing["total"] >= 1 and listing["items"][0]["id"] == paper_id)

    search = api("GET", f"/search?q={urllib.parse.quote('attention')}")
    check("FTS search", search["mode"] == "bm25" and search["total"] >= 1, f"{search['total']} hits")
    short = api("GET", f"/search?q={urllib.parse.quote('at')}")
    check("short query fallback", short["mode"] == "like", f"{short['total']} hits")
    check("search result page", any(item.get("page") for item in search["items"]), "page-aware")

    # --------------------------------------------------------------- summary
    summary = api("POST", f"/papers/{paper_id}/summarize")
    check("summary generated", bool(summary["summary"]) and summary["record_id"] > 0, summary["mode"])
    check("summary evidence", len(summary["evidence"]) >= 1, f"{len(summary['evidence'])} evidence items")
    check(
        "summary page citations",
        "(p." in summary["summary"] or "(abstract)" in summary["summary"],
    )
    history = api("GET", f"/papers/{paper_id}/summaries")
    check("summary history", any(item["id"] == summary["record_id"] for item in history["items"]))
    detail = api("GET", f"/papers/{paper_id}")
    check("summary persisted", detail["latest_summary"]["id"] == summary["record_id"])

    answer = api(
        "POST",
        f"/papers/{paper_id}/ask",
        {"question": "What problem does this paper address?"},
    )
    check("paper ask fallback", bool(answer["answer"]) and len(answer["citations"]) > 0, answer["mode"])

    # -------------------------------------------------------------- annotation
    annotation = api(
        "POST",
        f"/papers/{paper_id}/annotations",
        {"page": 1, "quote": "attention", "comment": "e2e annotation"},
    )
    detail = api("GET", f"/papers/{paper_id}")
    check("annotation create", detail["annotation_count"] == 1)
    api("DELETE", f"/papers/{paper_id}/annotations/{annotation['id']}")
    check("annotation delete", api("GET", f"/papers/{paper_id}")["annotation_count"] == 0)

    # -------------------------------------------------------------------- note
    note = api(
        "PUT",
        f"/papers/{paper_id}/note",
        {"body": "# E2E note\n\nEvidence-backed summary workflow. [[I0001]]"},
    )
    check("note save", note["ok"] is True)
    check(
        "note indexed",
        api("GET", f"/search?q={urllib.parse.quote('evidence-backed')}")["total"] >= 1,
    )

    # ------------------------------------------------------------------- idea
    idea = api(
        "POST",
        "/ideas",
        {
            "title": "E2E idea: link summary evidence to experiments",
            "summary": "Test the full research loop.",
            "inspired_by": [paper_id],
            "tags": ["e2e"],
        },
    )
    check("idea create", idea["id"].startswith("I"))
    check("idea markdown", bool(idea["body"]) and bool(idea["path"]))
    promoted = api("POST", f"/ideas/{idea['id']}/promote")
    experiment_id = promoted["experiment_id"]
    check("idea promote", experiment_id.startswith("E"))

    # -------------------------------------------------------------- experiment
    run = api(
        "POST",
        "/runs",
        {"experiment_id": experiment_id, "params": {"lr": 0.001, "e2e": True}, "seed": 7},
    )
    metrics = [
        {"key": "recall@20", "step": step, "value": 0.3 + step * 0.01}
        for step in range(1, 6)
    ]
    check("run create", run["id"].endswith("-R01"), run["id"])
    check(
        "metrics",
        api("POST", f"/runs/{run['id']}/metrics", {"metrics": metrics})["count"] == 5,
    )

    data_dir = Path(health["data_dir"])
    artifact_source = data_dir / "experiments" / experiment_id / "runs" / "e2e.png"
    artifact_source.parent.mkdir(parents=True, exist_ok=True)
    artifact_source.write_bytes((ROOT / "frontend" / "public" / "icon-192.png").read_bytes())
    artifact = api(
        "POST",
        f"/runs/{run['id']}/artifacts",
        {"kind": "figure", "path": str(artifact_source)},
    )
    check("artifact", artifact["id"] > 0)
    api("POST", f"/runs/{run['id']}/finish", {"summary": {"final": 0.35}})
    compare = api("GET", f"/experiments/{experiment_id}/compare?runs={run['id']}")
    check("run compare", compare["metric_keys"] == ["recall@20"])
    _artifact_response, artifact_bytes = api(
        "GET",
        f"/experiments/{experiment_id}/runs/{run['id']}/artifacts/{artifact['id']}",
        raw=True,
    )
    check("artifact download", artifact_bytes[:8] == b"\x89PNG\r\n\x1a\n")

    # ------------------------------------------------------------------ draft
    draft = api("POST", "/drafts", {"title": "E2E Draft", "venue": "TestConf"})
    body = (
        "# E2E Draft\n\n"
        "## 1. Introduction\n\n"
        f"We build on [@{paper['bibkey']}] and record evidence in the system.\n\n"
        "## 2. Experiment\n\n"
        f"{{{{run:{run['id']}/e2e.png}}}}\n"
    )
    updated = api(
        "PUT",
        f"/drafts/{draft['id']}",
        {"body": body, "title": "E2E Draft", "status": "writing"},
    )
    check("draft save", updated["word_count"] > 0, f"{updated['word_count']} words")
    _html_response, html_bytes = api(
        "GET", f"/drafts/{draft['id']}/export?format=html", raw=True
    )
    check("draft HTML export", b"<html" in html_bytes.lower() and b"E2E Draft" in html_bytes)
    check("draft citation rendered", b"Vaswani" in html_bytes or b"Attention" in html_bytes)
    _pdf_response, draft_pdf = api(
        "GET", f"/drafts/{draft['id']}/export?format=pdf", raw=True
    )
    check(
        "draft PDF export",
        draft_pdf.startswith(b"%PDF") and len(draft_pdf) > 10_000,
        f"{len(draft_pdf):,} bytes",
    )

    # ------------------------------------------------------------- links/graph
    links = api("GET", f"/links?entity_id={draft['id']}")
    check("links", links["total"] >= 1)
    graph = api("GET", "/graph")
    check("graph", len(graph["nodes"]) >= 4 and len(graph["edges"]) >= 1)

    # ------------------------------------------------------------------ inbox
    inbox = api("POST", "/inbox", {"content": "E2E inbox item"})
    check("inbox create", inbox["id"] > 0)
    check("inbox list", any(item["id"] == inbox["id"] for item in api("GET", "/inbox")["items"]))
    api("PATCH", f"/inbox/{inbox['id']}?processed=true")
    check("inbox process", api("GET", "/inbox?processed=true")["items"][0]["processed"] is True)
    api("DELETE", f"/inbox/{inbox['id']}")

    # ------------------------------------------------------------------- feed
    feed = api("POST", "/feed/refresh?limit=10")
    check("feed refresh", feed["fetched"] >= 1, str(feed))
    items = api("GET", "/feed?status=new")["items"]
    if len(items) >= 2:
        accepted = api("POST", f"/feed/{items[0]['id']}/accept")
        check("feed accept", accepted["status"] in {"importing", "already-imported"})
        if accepted.get("job_id"):
            wait_job(accepted["job_id"])
        check("feed ignore", api("POST", f"/feed/{items[1]['id']}/ignore")["ok"] is True)
    else:
        check("feed items available", False, "arXiv returned fewer than 2 items")

    # --------------------------------------------------------------- upload
    fixture = data_dir / "fixtures" / f"synthetic-{uuid.uuid4().hex[:8]}.pdf"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    synthetic_pdf(fixture)
    upload = upload_pdf(fixture)
    uploaded = wait_job(upload["job_id"])
    synthetic_id = uploaded["paper_id"]
    check("PDF upload", bool(synthetic_id), synthetic_id)
    synthetic_summary = api("POST", f"/papers/{synthetic_id}/summarize")
    check(
        "synthetic summary",
        len(synthetic_summary["evidence"]) >= 2,
        synthetic_summary["mode"],
    )
    duplicate = upload_pdf(fixture)
    deduped = wait_job(duplicate["job_id"])
    check("PDF duplicate detection", deduped["paper_id"] == synthetic_id, deduped["paper_id"])

    # --------------------------------------------------------------- settings
    patched = api("PATCH", "/settings", {"bm25_body_weight": 2.0})
    check("settings patch", patched["bm25_body_weight"] == 2.0)
    api("PATCH", "/settings", {"bm25_body_weight": 1.0})

    # -------------------------------------------------------------- operations
    reindex = api("POST", "/admin/reindex")
    check(
        "reindex",
        reindex["ok"] is True and reindex["fts_rows"] > 0,
        f"{reindex['fts_rows']} rows",
    )
    stats = api("GET", "/admin/stats")
    check("stats", stats["counts"]["paper"] >= 2)
    backup = api("POST", "/admin/backup")
    check("backup", Path(backup["path"]).exists() and backup["size"] > 0)
    backups = api("GET", "/admin/backups")
    check("backups list", len(backups["items"]) >= 1)

    elapsed = time.time() - started
    REPORT.write_text(
        "# Live end-to-end test\n\n"
        f"- Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- Base URL: `{BASE}`\n"
        f"- Checks: **{len(RESULTS)} passed**\n"
        f"- Duration: {elapsed:.1f}s\n\n"
        "| Check | Result | Detail |\n| --- | --- | --- |\n"
        + "\n".join(
            f"| {item['name']} | {item['status']} | {item['detail']} |"
            for item in RESULTS
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n{len(RESULTS)} checks passed in {elapsed:.1f}s")
    print(f"report: {REPORT}")


if __name__ == "__main__":
    main()
