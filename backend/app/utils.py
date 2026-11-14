from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import Session


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def loads(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def next_id(session: Session, prefix: str, width: int = 4) -> str:
    table_map = {"P": "paper", "I": "idea", "E": "experiment", "D": "draft"}
    session.execute(
        text("INSERT INTO counter(prefix, value) VALUES (:p, 0) ON CONFLICT(prefix) DO NOTHING"),
        {"p": prefix},
    )
    if prefix in table_map:
        table = table_map[prefix]
        # Repair counters when databases were populated manually or restored
        # from an older snapshot where the counter lagged behind.
        session.execute(
            text(
                f"UPDATE counter SET value = MAX(value, "
                f"(SELECT COALESCE(MAX(CAST(SUBSTR(id, 2) AS INTEGER)), 0) FROM {table} "
                f"WHERE id GLOB '{prefix}[0-9]*')) WHERE prefix = :p"
            ),
            {"p": prefix},
        )
    session.execute(
        text("UPDATE counter SET value = value + 1 WHERE prefix = :p"),
        {"p": prefix},
    )
    value = session.execute(
        text("SELECT value FROM counter WHERE prefix = :p"), {"p": prefix}
    ).scalar_one()
    return f"{prefix}{value:0{width}d}"


def slugify(value: str, max_len: int = 24) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value[:max_len]


def make_bibkey(session: Session, authors: list[str], year: int | None, title: str) -> str:
    family = "anon"
    if authors:
        first = authors[0]
        if "," in first:
            family = first.split(",")[0]
        else:
            bits = first.split()
            family = bits[-1] if bits else first
    family = slugify(family) or "anon"
    first_word = next((w for w in re.findall(r"[A-Za-z0-9]+", title) if len(w) > 2), "work")
    base = f"{family}{year or 'nd'}{slugify(first_word, 12)}"
    candidate = base
    n = 1
    while session.execute(
        text("SELECT 1 FROM paper WHERE bibkey = :k"), {"k": candidate}
    ).first():
        n += 1
        candidate = f"{base}{chr(96 + n)}"
    return candidate


def read_text(path: str | Path | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def write_text(path: str | Path, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def clip(value: str | None, length: int = 240) -> str:
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= length else value[: length - 1] + "…"


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
