from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from ..config import anthropic_key, load_settings
from ..models import Chunk, Paper
from ..utils import clip


def _candidate_chunks(session: Session, paper_id: str, question: str, limit: int = 8) -> list[Chunk]:
    q = (question or "").strip()
    if len(q) >= 3:
        terms = [t for t in re.split(r"\s+", q) if t]
        fts_q = " AND ".join('"' + t.replace('"', '""') + '"' for t in terms)
        try:
            rows = session.execute(
                text(
                    "SELECT row_id FROM search_fts "
                    "WHERE search_fts MATCH :q AND entity_id = :eid AND type = 'paper_chunk' "
                    "ORDER BY bm25(search_fts, 0, 0, 0, 0, 10.0, 1.0) ASC LIMIT :limit"
                ),
                {"q": fts_q, "eid": paper_id, "limit": limit},
            ).all()
            ids = [r[0] for r in rows]
            if ids:
                chunks = []
                for chunk_id in ids:
                    chunk = session.get(Chunk, chunk_id)
                    if chunk:
                        chunks.append(chunk)
                if chunks:
                    return chunks
        except Exception:
            pass
    rows = session.execute(
        text(
            "SELECT c.id FROM chunk c WHERE c.paper_id = :eid AND c.text LIKE :like LIMIT :limit"
        ),
        {"eid": paper_id, "like": f"%{q}%", "limit": limit},
    ).all()
    result = []
    for row in rows:
        chunk = session.get(Chunk, row[0])
        if chunk:
            result.append(chunk)
    if result:
        return result
    fallback = session.execute(
        text("SELECT id FROM chunk WHERE paper_id = :eid ORDER BY page, id LIMIT :limit"),
        {"eid": paper_id, "limit": min(limit, 4)},
    ).all()
    return [chunk for row in fallback if (chunk := session.get(Chunk, row[0])) is not None]


def ask_paper(session: Session, paper_id: str, question: str) -> dict[str, Any]:
    paper = session.get(Paper, paper_id)
    if not paper:
        raise ValueError("paper not found")
    chunks = [c for c in _candidate_chunks(session, paper_id, question) if c is not None]
    key = anthropic_key()
    citations = [
        {
            "page": chunk.page,
            "chunk_id": chunk.id,
            "text": clip(chunk.text, 320),
        }
        for chunk in chunks[:6]
    ]
    if not key:
        lines = ["当前未配置 `ANTHROPIC_API_KEY`，下面返回的是 **BM25 定位到的原文证据**，不是模型生成的答案。\n"]
        if chunks:
            lines.append("与问题最相关的原文片段：")
            for chunk in chunks[:4]:
                lines.append(f"- **p.{chunk.page or '?'}** — {clip(chunk.text, 280)}")
            lines.append("\n配置 API Key 后，同一检索结果会交给模型综合并给出带页码的答案。")
        else:
            lines.append("这篇论文还没有可用的全文分块。导入 PDF 后系统会自动抽取全文。")
        return {
            "answer": "\n".join(lines),
            "citations": citations,
            "mode": "local-extractive",
            "model": None,
        }

    settings = load_settings()
    model = settings.get("anthropic_model", "claude-sonnet-4-5")
    context = "\n\n".join(
        f"[第 {chunk.page or '?'} 页 | {chunk.id}]\n{chunk.text[:1600]}" for chunk in chunks[:8]
    )
    prompt = f"""你是严谨的学术研究助理。请只根据下面的论文片段回答问题。
如果片段不足以回答，请明确说“论文片段不足以回答”，不要编造。
回答使用中文，先给 2–4 句直接结论，再给证据要点。每个关键论断后用 (p.X) 标注页码。

论文标题：{paper.title}
用户问题：{question}

论文片段：
{context}
"""
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=key)
        message = client.messages.create(
            model=model,
            max_tokens=1400,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )
        return {
            "answer": answer,
            "citations": citations,
            "mode": "anthropic",
            "model": model,
        }
    except Exception as exc:
        return {
            "answer": (
                "模型调用失败，已保留 BM25 检索证据。\n\n"
                f"错误：`{type(exc).__name__}: {exc}`\n\n"
                + "\n".join(
                    f"- **p.{c.page or '?'}** — {clip(c.text, 260)}" for c in chunks[:4]
                )
            ),
            "citations": citations,
            "mode": "local-fallback",
            "model": model,
        }
