from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from ..config import anthropic_key, load_settings
from ..models import Chunk, Paper, SummaryRecord
from ..utils import clip, dumps, now_iso

prompt_version = "paper-summary/2026-11-14"

SECTIONS = {
    "problem": (
        "problem",
        "challenge",
        "we address",
        "aim",
        "motivation",
        "difficulty",
        "issue",
    ),
    "method": (
        "method",
        "approach",
        "architecture",
        "we propose",
        "we introduce",
        "we present",
        "framework",
        "algorithm",
        "objective",
        "design",
    ),
    "evidence": (
        "experiment",
        "result",
        "dataset",
        "outperform",
        "evaluation",
        "baseline",
        "improve",
        "accuracy",
        "recall",
        "ndcg",
        "bleu",
        "state-of-the-art",
        "achieves",
    ),
    "limitation": (
        "limitation",
        "however",
        "future work",
        "fail",
        "constraint",
        "drawback",
        "not support",
    ),
}


@dataclass
class Evidence:
    role: str
    page: int | None
    chunk_id: str
    quote: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "quote": self.quote,
        }


def _split_sentences(value: str) -> list[str]:
    value = re.sub(r"\s+", " ", value or "").strip()
    parts = re.split(r"(?<=[.!?。！？])\s+", value)
    return [part.strip() for part in parts if 48 <= len(part.strip()) <= 380]


NOISE = (
    "acknowledg",
    "work performed",
    "provided proper attribution",
    "conference on neural information",
    "all rights reserved",
    "corresponding author",
    "<eos>",
    "<pad>",
)


def _score_sentence(sentence: str, terms: tuple[str, ...], section_bonus: float = 0.0) -> float:
    lowered = sentence.lower()
    if any(token in lowered for token in NOISE):
        return 0.0
    if lowered.startswith(("figure ", "table ")) or "figure 3:" in lowered:
        return 0.0
    if not any(term in lowered for term in terms):
        return 0.0
    score = section_bonus
    for index, term in enumerate(terms):
        if term in lowered:
            score += 1.0 + (len(terms) - index) * 0.08
    # Prefer informative, readable sentences over fragments with many citations.
    citation_density = lowered.count("[") + lowered.count("†") + lowered.count("∗")
    score += 0.25 if 90 <= len(sentence) <= 260 else 0.0
    score -= min(citation_density, 4) * 0.35
    return score


def _chunk_sections(chunks: list[Chunk]) -> dict[str, str]:
    headings = {
        "abstract": "problem",
        "introduction": "problem",
        "background": "problem",
        "related work": "problem",
        "model architecture": "method",
        "model": "method",
        "architecture": "method",
        "method": "method",
        "approach": "method",
        "training": "method",
        "experiment": "evidence",
        "results": "evidence",
        "evaluation": "evidence",
        "analysis": "evidence",
        "discussion": "limitation",
        "conclusion": "limitation",
        "limitations": "limitation",
        "references": "ignore",
        "bibliography": "ignore",
        "appendix": "ignore",
        "supplementary": "ignore",
        "acknowledg": "ignore",
        "attention visualizations": "ignore",
    }
    current = "problem"
    mapping: dict[str, str] = {}
    for chunk in chunks:
        lower = chunk.text.lower()
        if current == "ignore":
            mapping[chunk.id] = "ignore"
            continue
        if re.search(r"(^|\n)\s*references\s*(\n|$)", lower):
            current = "ignore"
            mapping[chunk.id] = "ignore"
            continue
        citation_marks = len(re.findall(r"\[\d+\]", lower))
        reference_marks = lower.count("arxiv preprint") + lower.count("et al.") + lower.count("proceedings of")
        if citation_marks >= 8 and reference_marks >= 2:
            current = "ignore"
            mapping[chunk.id] = "ignore"
            continue
        for heading, role in headings.items():
            if re.search(rf"(^|\n)\s*(?:\d+(?:\.\d+)*\s*)?{re.escape(heading)}\b", lower):
                current = role
        mapping[chunk.id] = current
    return mapping


def _select_evidence(session: Session, paper: Paper, per_role: int = 2) -> list[Evidence]:
    chunks = session.exec(
        select(Chunk).where(Chunk.paper_id == paper.id).order_by(Chunk.page, Chunk.id)
    ).all()
    sections = _chunk_sections(chunks)
    selected: list[Evidence] = []
    seen: set[str] = set()
    abstract_sentences = _split_sentences(paper.abstract or "")
    minimum = {"problem": 1.0, "method": 1.5, "evidence": 1.5, "limitation": 1.2}

    for role, terms in SECTIONS.items():
        scored: list[tuple[float, int | None, str, str]] = []
        if role in {"problem", "method", "evidence"}:
            for index, sentence in enumerate(abstract_sentences[:8]):
                score = _score_sentence(sentence, terms, section_bonus=1.5)
                if role == "problem" and index == 0:
                    score = max(score, 1.6)
                if score > 0:
                    scored.append((score, None, "abstract", sentence))
        for chunk in chunks:
            section_role = sections.get(chunk.id, "problem")
            if section_role == "ignore" or section_role != role:
                continue
            for sentence in _split_sentences(chunk.text):
                score = _score_sentence(sentence, terms, section_bonus=2.1)
                if score > 0:
                    scored.append((score, chunk.page, chunk.id, sentence))
        scored.sort(key=lambda item: item[0], reverse=True)
        added = 0
        used_chunks: set[str] = set()
        for score, page, chunk_id, sentence in scored:
            if score < minimum[role]:
                continue
            normalized = sentence.lower()[:160]
            if normalized in seen:
                continue
            if chunk_id != "abstract" and chunk_id in used_chunks:
                continue
            seen.add(normalized)
            used_chunks.add(chunk_id)
            selected.append(
                Evidence(
                    role=role,
                    page=page,
                    chunk_id=chunk_id,
                    quote=clip(sentence, 360),
                )
            )
            added += 1
            if added >= per_role:
                break

    if not any(item.role == "problem" for item in selected) and abstract_sentences:
        selected.insert(
            0,
            Evidence(
                role="problem",
                page=None,
                chunk_id="abstract",
                quote=clip(abstract_sentences[0], 360),
            ),
        )
    return selected[:10]


def _evidence_by_role(evidence: list[Evidence], role: str, limit: int = 2) -> list[Evidence]:
    return [item for item in evidence if item.role == role][:limit]


def _citation(item: Evidence) -> str:
    return f"(p.{item.page})" if item.page else "(abstract)"


class PaperSummaryAgent:
    """Structured paper summary with page-level evidence and an audit record."""

    def __init__(self, provider: str = "auto") -> None:
        self.provider = provider

    def summarize(self, session: Session, paper_id: str) -> dict[str, Any]:
        paper = session.get(Paper, paper_id)
        if not paper:
            raise ValueError("paper not found")

        evidence = _select_evidence(session, paper)
        key = anthropic_key()
        mode = "local-extractive"
        model: str | None = None
        summary = self._local_summary(paper, evidence)

        if self.provider not in {"local", "recorded"} and key:
            settings = load_settings()
            model = settings.get("anthropic_model", "claude-sonnet-4-5")
            try:
                summary = self._llm_summary(paper, evidence, key, model)
                mode = "anthropic"
            except Exception as exc:  # keep evidence and degrade gracefully
                mode = "local-fallback"
                summary = (
                    f"> LLM 调用失败，已回退到本地证据摘要：`{type(exc).__name__}: {exc}`\n\n"
                    + summary
                )

        record = SummaryRecord(
            paper_id=paper_id,
            mode=mode,
            model=model,
            summary=summary,
            evidence=dumps([item.as_dict() for item in evidence]),
            prompt_version=prompt_version,
            created_at=now_iso(),
        )
        session.add(record)
        paper.ai_summary = summary
        paper.updated_at = now_iso()
        session.add(paper)
        session.flush()

        return {
            "record_id": record.id,
            "summary": summary,
            "mode": mode,
            "model": model,
            "evidence": [item.as_dict() for item in evidence],
            "prompt_version": prompt_version,
            "created_at": record.created_at,
        }

    # ------------------------------------------------------------------ local

    def _local_summary(self, paper: Paper, evidence: list[Evidence]) -> str:
        settings = load_settings()
        focus = settings.get("research_focus") or settings.get("research_field") or "your research"
        problem = _evidence_by_role(evidence, "problem") or [
            Evidence("problem", None, "abstract", clip(paper.abstract, 360))
        ]
        method = _evidence_by_role(evidence, "method")
        result = _evidence_by_role(evidence, "evidence")
        limits = _evidence_by_role(evidence, "limitation")

        def bullets(items: list[Evidence], empty: str) -> str:
            if not items:
                return f"- {empty}"
            return "\n".join(f"- {item.quote} {_citation(item)}" for item in items)

        return f"""> **本地证据摘要** · 未调用 LLM · 以下内容是从 PDF 分块中提取的原文证据，不是模型生成的综合判断。
> 你可以配置 `ANTHROPIC_API_KEY` 后重新生成；每次摘要及其证据都会写入 `summary_record`。

### 问题
{bullets(problem, "检索片段中没有明确的问题陈述。")}

### 方法
{bullets(method, "检索片段中没有明确的方法描述；请阅读全文补充。")}

### 证据
{bullets(result, "检索片段中没有明确的实验或结果陈述。")}

### 局限
{bullets(limits, "检索片段没有明确陈述局限。")}

### 与你当前方向的关系
当前研究焦点：**{focus}**。

上述证据只说明论文本身；它是否支持你的方向，需要你把机制、数据和评价协议对齐后再判断。可用问题：这篇论文的哪个模块可以被替换？它的评价是否能区分社会关系带来的增益？

### 可追溯性
- 论文：`{paper.id}` · {paper.title}
- 证据条目：{len(evidence)} 条，来自 PDF 分块或摘要
- 生成模式：`local-extractive`
"""

    # -------------------------------------------------------------------- llm

    def _llm_summary(
        self, paper: Paper, evidence: list[Evidence], key: str, model: str
    ) -> str:
        from anthropic import Anthropic

        context = "\n\n".join(
            f"[{item.role} | p.{item.page or 'abstract'} | {item.chunk_id}]\n{item.quote}"
            for item in evidence
        )
        prompt = f"""你是严谨的学术研究助理。请只根据给定证据，为论文写一份结构化摘要。

要求：
1. 使用中文，严格分为：问题、方法、证据、局限、与生成式推荐/社交推荐的潜在关系。
2. 每个关键论断后用 (p.X) 标注页码；如果证据只来自摘要，用 (abstract)。
3. 不要编造数据集、数字或结论；证据不足时明确写“证据不足”。
4. 区分“论文声称”与“你的判断”。

论文标题：{paper.title}
作者：{paper.authors or "unknown"}
年份：{paper.year or "unknown"}

证据：
{context}
"""
        client = Anthropic(api_key=key)
        message = client.messages.create(
            model=model,
            max_tokens=1200,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        ).strip()


def summary_history(session: Session, paper_id: str, limit: int = 8) -> list[dict[str, Any]]:
    records = session.exec(
        select(SummaryRecord)
        .where(SummaryRecord.paper_id == paper_id)
        .order_by(SummaryRecord.created_at.desc())
        .limit(limit)
    ).all()
    items = []
    for record in records:
        try:
            evidence = json.loads(record.evidence or "[]")
        except json.JSONDecodeError:
            evidence = []
        items.append(
            {
                "id": record.id,
                "mode": record.mode,
                "model": record.model,
                "summary": record.summary,
                "evidence": evidence,
                "prompt_version": record.prompt_version,
                "created_at": record.created_at,
            }
        )
    return items


def latest_summary(session: Session, paper_id: str) -> dict[str, Any] | None:
    rows = summary_history(session, paper_id, limit=1)
    return rows[0] if rows else None
