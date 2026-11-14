from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

APP_NAME = "Lattice"
APP_SUBTITLE = "生成式推荐 · 社交关系推荐 研究工作台"
VERSION = "0.1.0"

DATA_DIR = Path(
    os.environ.get("RESEARCH_DATA_DIR", str(Path.home() / "research-data"))
).expanduser().resolve()

PAPERS_DIR = DATA_DIR / "papers"
NOTES_DIR = DATA_DIR / "notes"
IDEAS_DIR = DATA_DIR / "ideas"
EXPERIMENTS_DIR = DATA_DIR / "experiments"
DRAFTS_DIR = DATA_DIR / "drafts"
LOGS_DIR = DATA_DIR / "logs"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
CONFIG_PATH = DATA_DIR / "config.json"
DB_PATH = DATA_DIR / "app.db"

ALL_DIRS = [
    DATA_DIR,
    PAPERS_DIR,
    NOTES_DIR,
    IDEAS_DIR,
    EXPERIMENTS_DIR,
    DRAFTS_DIR,
    LOGS_DIR,
    ATTACHMENTS_DIR,
]

DEFAULT_SETTINGS: dict[str, Any] = {
    "research_field": "生成式推荐系统",
    "research_focus": "社交关系推荐",
    "research_questions": [
        "这个系统要解决的第一个具体问题是什么？",
        "什么证据会让我改变当前判断？",
        "最小的可证伪实验是什么？",
    ],
    "arxiv_keywords": [
        "generative recommendation",
        "social recommendation",
        "semantic id",
        "graph neural network recommender",
        "LLM recommender",
        "diffusion recommender",
    ],
    "arxiv_categories": ["cs.IR", "cs.SI", "cs.LG"],
    "bm25_title_weight": 10.0,
    "bm25_body_weight": 1.0,
    "anthropic_model": "claude-sonnet-4-5",
    "daily_feed_enabled": True,
    "daily_feed_hour": 8,
    "theme": "paper",
}


def ensure_dirs() -> None:
    for directory in ALL_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_settings({})


def load_settings() -> dict[str, Any]:
    ensure_dirs()
    data = dict(DEFAULT_SETTINGS)
    if CONFIG_PATH.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            data.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    return data


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    current = dict(DEFAULT_SETTINGS)
    if CONFIG_PATH.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            current.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    current.update({k: v for k, v in patch.items() if v is not None})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return current


def anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or load_settings().get("anthropic_api_key")


def public_settings() -> dict[str, Any]:
    settings = load_settings()
    settings.pop("anthropic_api_key", None)
    settings["has_anthropic_key"] = bool(anthropic_key())
    settings["data_dir"] = str(DATA_DIR)
    settings["db_path"] = str(DB_PATH)
    settings["version"] = VERSION
    return settings
