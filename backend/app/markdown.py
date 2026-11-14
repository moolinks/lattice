from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter
import yaml


@dataclass
class MarkdownDoc:
    meta: dict[str, Any] = field(default_factory=dict)
    body: str = ""


def parse_markdown(path: str | Path) -> MarkdownDoc:
    p = Path(path)
    if not p.exists():
        return MarkdownDoc()
    try:
        post = frontmatter.loads(p.read_text(encoding="utf-8"))
        return MarkdownDoc(meta=dict(post.metadata), body=post.content)
    except Exception:
        return MarkdownDoc(body=p.read_text(encoding="utf-8", errors="replace"))


def dump_markdown(meta: dict[str, Any], body: str) -> str:
    clean = {k: v for k, v in meta.items() if v is not None and v != ""}
    if not clean:
        return body.rstrip() + "\n"
    header = yaml.safe_dump(
        clean, allow_unicode=True, sort_keys=False, default_flow_style=None
    ).strip()
    return f"---\n{header}\n---\n\n{body.strip()}\n"
