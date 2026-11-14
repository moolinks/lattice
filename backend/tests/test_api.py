from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="lattice-test-"))
os.environ["RESEARCH_DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["RESEARCH_HUB_SCHEDULER"] = "0"
os.environ["RESEARCH_HUB_WATCHER"] = "0"

import pytest
from fastapi.testclient import TestClient

from app.config import DRAFTS_DIR, IDEAS_DIR, NOTES_DIR
from app.db import init_db, session_scope
from app.markdown import dump_markdown
from app.models import Chunk, Draft, Idea, Paper
from app.services.indexer import index_draft, index_idea, index_paper
from app.utils import dumps, now_iso, write_text


@pytest.fixture(scope="session")
def client():
    init_db()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def seeded(client):
    with session_scope() as session:
        paper = Paper(
            id="P0001",
            title="A Synthetic Paper for Lattice Tests",
            authors=dumps(["Ada Lovelace", "Alan Turing"]),
            year=2025,
            venue="TestConf",
            abstract="A local research system needs reliable ingestion, search and traceable summaries.",
            bibkey="lovelace2025synthetic",
            status="reading",
            note_path=str(NOTES_DIR / "P0001.md"),
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        write_text(
            paper.note_path,
            dump_markdown(
                {"id": "P0001", "title": paper.title, "status": "reading"},
                "# Note\n\nSearch and summaries should be traceable. Linking [[I0001]].\n",
            ),
        )
        session.add(paper)
        session.flush()
        session.add(
            Chunk(
                id="P0001-C0001",
                paper_id="P0001",
                page=2,
                text=(
                    "We propose an evidence-first workflow for local research. "
                    "Experiments show that page-level citations improve summary review."
                ),
            )
        )
        session.flush()
        index_paper(session, paper)
        idea = Idea(
            id="I0001",
            title="A test hypothesis",
            status="hypothesis",
            priority=80,
            summary="A synthetic hypothesis for the test fixture.",
            path=str(IDEAS_DIR / "I0001.md"),
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        write_text(
            idea.path,
            dump_markdown(
                {"id": "I0001", "title": idea.title, "status": idea.status, "inspired_by": ["P0001"]},
                "## Hypothesis\n\nA simple testable claim. See [[P0001]].\n",
            ),
        )
        session.add(idea)
        session.flush()
        index_idea(session, idea)
        draft = Draft(
            id="D0001",
            title="A Test Draft",
            venue="TestConf",
            status="writing",
            path=str(DRAFTS_DIR / "D0001" / "main.md"),
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        (DRAFTS_DIR / "D0001").mkdir(parents=True, exist_ok=True)
        write_text(
            draft.path,
            dump_markdown(
                {"id": "D0001", "title": draft.title},
                "# A Test Draft\n\nWe build on [@lovelace2025synthetic].\n",
            ),
        )
        session.add(draft)
        session.flush()
        index_draft(session, draft)
        from app.services.linker import sync_links

        sync_links(session, "D0001", {"id": "D0001"}, "# Draft\n\n[@lovelace2025synthetic]")
    return TEST_DATA_DIR


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["fts5"] == "ok"


def test_library_and_search(client, seeded):
    response = client.get("/api/papers")
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "P0001"

    response = client.get("/api/search", params={"q": "synthetic"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "bm25"
    assert any(item["entity_id"] in {"P0001", "I0001"} for item in payload["items"])

    short = client.get("/api/search", params={"q": "sy"})
    assert short.status_code == 200
    assert short.json()["mode"] == "like"


def test_paper_detail_note_and_annotation(client, seeded):
    detail = client.get("/api/papers/P0001").json()
    assert detail["note"]["body"]
    response = client.put(
        "/api/papers/P0001/note",
        json={"body": "# Updated note\n\nSearch and summaries should stay traceable. [[I0001]]"},
    )
    assert response.status_code == 200
    annotation = client.post(
        "/api/papers/P0001/annotations",
        json={"page": 2, "quote": "traceable", "comment": "test annotation"},
    )
    assert annotation.status_code == 200
    detail = client.get("/api/papers/P0001").json()
    assert detail["annotation_count"] == 1


def test_summary_agent(client, seeded):
    response = client.post("/api/papers/P0001/summarize")
    assert response.status_code == 200
    result = response.json()
    assert result["summary"]
    assert result["record_id"] > 0
    assert result["evidence"]
    assert "(p." in result["summary"] or "(abstract)" in result["summary"]
    history = client.get("/api/papers/P0001/summaries").json()
    assert any(item["id"] == result["record_id"] for item in history["items"])
    detail = client.get("/api/papers/P0001").json()
    assert detail["latest_summary"]["id"] == result["record_id"]


def test_ideas_and_links(client, seeded):
    response = client.post(
        "/api/ideas",
        json={
            "title": "A generated test idea",
            "summary": "A falsifiable test claim",
            "inspired_by": ["P0001"],
            "tags": ["test"],
        },
    )
    assert response.status_code == 200
    idea = response.json()
    assert idea["id"].startswith("I")
    assert (IDEAS_DIR / f"{idea['id']}.md").exists()
    links = client.get("/api/links", params={"entity_id": idea["id"]}).json()
    assert links["total"] >= 1
    graph = client.get("/api/graph").json()
    assert any(node["id"] == idea["id"] for node in graph["nodes"])


def test_experiment_run_compare(client, seeded):
    experiment = client.post(
        "/api/experiments",
        json={"title": "A test experiment", "hypothesis": "The test claim holds.", "idea_id": "I0001"},
    ).json()
    run = client.post(
        "/api/runs",
        json={"experiment_id": experiment["id"], "params": {"lr": 0.001}, "seed": 42},
    ).json()
    assert run["id"].endswith("-R01")
    metrics = [
        {"key": "recall@20", "step": step, "value": 0.3 + step * 0.01}
        for step in range(1, 6)
    ]
    assert client.post(f"/api/runs/{run['id']}/metrics", json={"metrics": metrics}).status_code == 200
    finished = client.post(f"/api/runs/{run['id']}/finish", json={"summary": {"final": 0.35}})
    assert finished.status_code == 200
    compare = client.get(
        f"/api/experiments/{experiment['id']}/compare", params={"runs": run["id"]}
    )
    assert compare.status_code == 200
    assert compare.json()["metric_keys"] == ["recall@20"]


def test_draft_export_and_settings(client, seeded):
    response = client.get("/api/drafts/D0001/export", params={"format": "html"})
    assert response.status_code == 200
    assert "A Test Draft" in response.text
    settings = client.get("/api/settings").json()
    assert settings["research_field"]
    updated = client.patch("/api/settings", json={"bm25_body_weight": 2.0})
    assert updated.status_code == 200
    assert updated.json()["bm25_body_weight"] == 2.0


def test_reindex(client, seeded):
    report = client.post("/api/admin/reindex").json()
    assert report["ok"] is True
    assert report["papers"] >= 1
    assert report["drafts"] >= 1
