from __future__ import annotations

import re
import shutil
import threading
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import bibtexparser
import httpx
import pymupdf as fitz
from sqlalchemy import text
from sqlmodel import Session, select

from ..config import ATTACHMENTS_DIR, NOTES_DIR, PAPERS_DIR
from ..db import session_scope
from ..markdown import dump_markdown
from ..models import Chunk, EntityTag, ImportJob, Paper, Tag
from ..utils import dumps, loads, make_bibkey, next_id, now_iso, write_text
from .indexer import index_paper
from .linker import sync_links

ARXIV_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)?(?P<id>\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?", re.I
)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
ATOM = {"a": "http://www.w3.org/2005/Atom"}


def _progress(job_id: str, progress: int, message: str, status: str = "running") -> None:
    with session_scope() as session:
        job = session.get(ImportJob, job_id)
        if job:
            job.progress = progress
            job.message = message
            job.status = status
            job.updated_at = now_iso()
            if status in ("failed", "complete"):
                job.message = message


def _complete(job_id: str, paper_id: str, message: str = "导入完成") -> None:
    with session_scope() as session:
        job = session.get(ImportJob, job_id)
        if job:
            job.progress = 100
            job.status = "complete"
            job.message = message
            job.paper_id = paper_id
            job.updated_at = now_iso()


def _fail(job_id: str, message: str) -> None:
    with session_scope() as session:
        job = session.get(ImportJob, job_id)
        if job:
            job.status = "failed"
            job.message = message[:500]
            job.updated_at = now_iso()


def fetch_arxiv(arxiv_id: str) -> dict[str, Any]:
    url = "https://export.arxiv.org/api/query"
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(url, params={"id_list": arxiv_id})
        response.raise_for_status()
    root = ET.fromstring(response.text)
    entry = root.find("a:entry", ATOM)
    if entry is None:
        raise ValueError(f"arXiv 上找不到 {arxiv_id}")
    title = " ".join((entry.findtext("a:title", default="", namespaces=ATOM)).split())
    abstract = " ".join((entry.findtext("a:summary", default="", namespaces=ATOM)).split())
    authors = [
        " ".join((node.findtext("a:name", default="", namespaces=ATOM)).split())
        for node in entry.findall("a:author", ATOM)
    ]
    published = entry.findtext("a:published", default="", namespaces=ATOM)
    year = int(published[:4]) if published[:4].isdigit() else None
    journal = entry.findtext(
        "{http://arxiv.org/schemas/atom}journal_ref", default="", namespaces=ATOM
    )
    return {
        "title": title,
        "abstract": abstract,
        "authors": [a for a in authors if a],
        "year": year,
        "venue": journal or "arXiv",
        "arxiv_id": arxiv_id,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "doi": entry.findtext("{http://arxiv.org/schemas/atom}doi", default=None, namespaces=ATOM),
    }


def fetch_crossref(doi: str) -> dict[str, Any]:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(f"https://api.crossref.org/works/{doi}")
        response.raise_for_status()
    message = response.json()["message"]
    authors = []
    for author in message.get("author", []):
        name = " ".join(x for x in [author.get("given"), author.get("family")] if x)
        if name:
            authors.append(name)
    date_parts = (
        message.get("published-print")
        or message.get("published-online")
        or message.get("issued")
        or {}
    ).get("date-parts", [[None]])
    year = date_parts[0][0] if date_parts and date_parts[0] else None
    return {
        "title": (message.get("title") or ["Untitled"])[0],
        "abstract": re.sub(r"<[^>]+>", "", message.get("abstract") or ""),
        "authors": authors,
        "year": year,
        "venue": (message.get("container-title") or [message.get("publisher", "")])[0],
        "doi": doi,
        "url": message.get("URL") or f"https://doi.org/{doi}",
    }


def parse_bibtex(source: str) -> dict[str, Any]:
    try:
        library = bibtexparser.loads(source)
        if not library.entries:
            raise ValueError("BibTeX 中没有条目")
        entry = library.entries[0]
    except Exception as exc:
        raise ValueError(f"BibTeX 解析失败：{exc}") from exc
    authors = [
        a.strip() for a in re.split(r"\s+and\s+", entry.get("author", "")) if a.strip()
    ]
    year_raw = entry.get("year", "")
    return {
        "title": re.sub(r"[{}]", "", entry.get("title", "Untitled")),
        "abstract": re.sub(r"[{}]", "", entry.get("abstract", "")),
        "authors": authors,
        "year": int(year_raw) if str(year_raw).isdigit() else None,
        "venue": entry.get("journal") or entry.get("booktitle") or entry.get("publisher") or "",
        "doi": entry.get("doi"),
        "arxiv_id": clean_arxiv_id(entry.get("eprint", "")) if entry.get("eprint") else None,
        "url": entry.get("url"),
        "bibkey": entry.get("ID"),
        "bibtex": bibtexparser.dumps(library).strip(),
    }


def clean_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    match = ARXIV_RE.search(value)
    return match.group("id") if match else None


def infer_source(source: str) -> tuple[str, str]:
    source = source.strip()
    if source.startswith("@") or ("\n" in source and "{" in source):
        return "bibtex", source
    arxiv_id = clean_arxiv_id(source)
    if arxiv_id and ("arxiv" in source.lower() or re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", source)):
        return "arxiv", arxiv_id
    doi_match = DOI_RE.search(source)
    if doi_match:
        return "doi", doi_match.group(1).rstrip(".,;)")
    raise ValueError("无法识别来源。请输入 arXiv ID/链接、DOI、BibTeX 或上传 PDF。")


def pdf_metadata(path: Path) -> dict[str, Any]:
    doc = fitz.open(path)
    meta = doc.metadata or {}
    title = (meta.get("title") or "").strip()
    if not title and doc.page_count:
        first = doc[0].get_text("text")[:1200]
        lines = [line.strip() for line in first.splitlines() if len(line.strip()) > 12]
        title = lines[0] if lines else path.stem
    authors = [a.strip() for a in re.split(r"[;,]", meta.get("author", "")) if a.strip()]
    year = None
    for key in ("creationDate", "modDate"):
        date = meta.get(key) or ""
        match = re.search(r"(20\d{2}|19\d{2})", date)
        if match:
            year = int(match.group(1))
            break
    doc.close()
    return {"title": title or path.stem, "authors": authors, "year": year, "venue": ""}


def _split_text(text_value: str, limit: int = 1300) -> list[str]:
    text_value = re.sub(r"[ \t]+", " ", text_value or "")
    text_value = re.sub(r"\n{3,}", "\n\n", text_value).strip()
    if not text_value:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text_value) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= limit:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                chunks.append(current)
            if len(paragraph) <= limit:
                current = paragraph
            else:
                sentences = re.split(r"(?<=[。！？.!?])\s*", paragraph)
                buffer = ""
                for sentence in sentences:
                    if len(buffer) + len(sentence) <= limit:
                        buffer += sentence
                    else:
                        if buffer:
                            chunks.append(buffer.strip())
                        buffer = sentence
                current = buffer.strip()
    if current:
        chunks.append(current)
    return [c for c in chunks if len(c) >= 40]


def extract_chunks(pdf_path: Path, paper_id: str) -> list[Chunk]:
    doc = fitz.open(pdf_path)
    chunks: list[Chunk] = []
    number = 1
    for page_index, page in enumerate(doc):
        page_text = page.get_text("text")
        for piece in _split_text(page_text):
            chunks.append(
                Chunk(
                    id=f"{paper_id}-C{number:04d}",
                    paper_id=paper_id,
                    page=page_index + 1,
                    text=piece,
                )
            )
            number += 1
    doc.close()
    return chunks


def make_bibtex(
    paper_id: str,
    title: str,
    authors: list[str],
    year: int | None,
    venue: str,
    doi: str | None,
    arxiv_id: str | None,
    bibkey: str,
) -> str:
    author_text = " and ".join(authors) if authors else "Unknown"
    fields = [
        f"  title = {{{title}}}",
        f"  author = {{{author_text}}}",
        f"  year = {{{year or ''}}}",
    ]
    if venue:
        fields.append(f"  journal = {{{venue}}}")
    if doi:
        fields.append(f"  doi = {{{doi}}}")
    if arxiv_id:
        fields.append(f"  eprint = {{{arxiv_id}}}")
        fields.append("  archivePrefix = {arXiv}")
    fields.append(f"  note = {{Research Hub {paper_id}}}")
    return f"@article{{{bibkey},\n" + ",\n".join(fields) + "\n}"


def ensure_tag(session: Session, name: str) -> Tag:
    name = name.strip()
    existing = session.exec(select(Tag).where(Tag.name == name)).first()
    if existing:
        return existing
    tag = Tag(name=name)
    session.add(tag)
    session.flush()
    return tag


def set_paper_tags(session: Session, paper_id: str, tags: list[str]) -> None:
    session.execute(
        text("DELETE FROM entity_tag WHERE entity_id = :eid"),
        {"eid": paper_id},
    )
    for name in dict.fromkeys(t for t in tags if t.strip()):
        tag = ensure_tag(session, name)
        session.add(EntityTag(entity_id=paper_id, tag_id=tag.id))


def note_body(paper: Paper, abstract: str) -> str:
    return f"""# {paper.title}

> **{', '.join(loads(paper.authors, [])) if paper.authors else 'Unknown'}** · {paper.year or '—'} · {paper.venue or ''}

## 一句话结论

（用自己的话写：这篇论文到底解决了什么？）

## 问题设定

{abstract[:900] if abstract else '（摘要未获取）'}

## 核心方法

- 尚未填写。

## 实验与证据

- 数据集：
- 基线：
- 关键数字：

## 与「生成式推荐 × 社交关系」的关系

- 生成式建模：
- 社交结构：
- 可迁移之处：

## 可攻击的点 / 我的假设

- 尚未填写。

## 相关

- 尚未填写。
"""


def persist_paper(
    session: Session,
    meta: dict[str, Any],
    pdf_source: Path | None = None,
    uploaded_pdf: Path | None = None,
) -> Paper:
    arxiv_id = clean_arxiv_id(meta.get("arxiv_id"))
    doi = meta.get("doi")
    title = (meta.get("title") or "Untitled").strip()

    def _duplicate(paper: Paper) -> Paper:
        if uploaded_pdf and uploaded_pdf.exists():
            uploaded_pdf.unlink(missing_ok=True)
        return paper

    if arxiv_id:
        existing = session.exec(select(Paper).where(Paper.arxiv_id == arxiv_id)).first()
        if existing:
            return _duplicate(existing)
    if doi:
        existing = session.exec(select(Paper).where(Paper.doi == doi)).first()
        if existing:
            return _duplicate(existing)
    if title and title.lower() != "untitled":
        row = session.execute(
            text("SELECT id FROM paper WHERE lower(title) = lower(:title) LIMIT 1"),
            {"title": title},
        ).first()
        if row:
            existing = session.get(Paper, row[0])
            if existing:
                return _duplicate(existing)

    paper_id = next_id(session, "P")
    authors = [str(a).strip() for a in meta.get("authors") or [] if str(a).strip()]
    year = meta.get("year")
    venue = meta.get("venue") or ""
    bibkey = meta.get("bibkey") or make_bibkey(session, authors, year, title)
    pdf_path = PAPERS_DIR / f"{paper_id}.pdf"

    if uploaded_pdf and uploaded_pdf.exists():
        shutil.move(str(uploaded_pdf), pdf_path)
    elif pdf_source and pdf_source.exists():
        shutil.move(str(pdf_source), pdf_path)
    else:
        pdf_path = None  # type: ignore[assignment]

    timestamp = now_iso()
    paper = Paper(
        id=paper_id,
        title=title,
        authors=dumps(authors),
        year=year,
        venue=venue,
        abstract=(meta.get("abstract") or "").strip() or None,
        doi=doi or None,
        arxiv_id=arxiv_id,
        url=meta.get("url"),
        pdf_path=str(pdf_path) if pdf_path else None,
        bibkey=bibkey,
        bibtex=meta.get("bibtex")
        or make_bibtex(paper_id, title, authors, year, venue, doi, arxiv_id, bibkey),
        status="unread",
        note_path=str(NOTES_DIR / f"{paper_id}.md"),
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(paper)
    session.flush()

    write_text(paper.note_path, dump_markdown(
        {
            "id": paper_id,
            "title": title,
            "status": "unread",
            "tags": meta.get("tags") or [],
            "inspired_by": [],
            "created": timestamp,
        },
        note_body(paper, meta.get("abstract") or ""),
    ))
    set_paper_tags(session, paper_id, meta.get("tags") or [])
    if paper.pdf_path and Path(paper.pdf_path).exists():
        for chunk in extract_chunks(Path(paper.pdf_path), paper_id):
            session.add(chunk)
        session.flush()
    index_paper(session, paper)
    sync_links(
        session,
        paper_id,
        {"id": paper_id, "title": title},
        "",
    )
    return paper


def _download_pdf(url: str, target: Path) -> bool:
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as handle:
                    for block in response.iter_bytes():
                        handle.write(block)
        if target.stat().st_size < 20_000:
            target.unlink(missing_ok=True)
            return False
        return True
    except Exception:
        target.unlink(missing_ok=True)
        return False


def run_import(job_id: str) -> None:
    try:
        with session_scope() as session:
            job = session.get(ImportJob, job_id)
            if not job:
                return
            kind, source = job.kind, job.source
        _progress(job_id, 8, "解析来源")

        upload_path: Path | None = None
        if kind == "pdf":
            upload_path = Path(source)
            meta = pdf_metadata(upload_path)
            _progress(job_id, 22, "读取 PDF 元数据")
        elif kind == "bibtex":
            meta = parse_bibtex(source)
            _progress(job_id, 22, "读取 BibTeX")
            if meta.get("arxiv_id"):
                try:
                    arxiv_meta = fetch_arxiv(meta["arxiv_id"])
                    arxiv_meta.update({k: v for k, v in meta.items() if v})
                    meta = arxiv_meta
                except Exception:
                    pass
            elif meta.get("doi"):
                try:
                    crossref_meta = fetch_crossref(meta["doi"])
                    crossref_meta.update({k: v for k, v in meta.items() if v})
                    meta = crossref_meta
                except Exception:
                    pass
        elif kind == "arxiv":
            _progress(job_id, 18, "请求 arXiv 元数据")
            meta = fetch_arxiv(source)
        elif kind == "doi":
            _progress(job_id, 18, "请求 Crossref 元数据")
            meta = fetch_crossref(source)
        else:
            detected_kind, detected = infer_source(source)
            if detected_kind != kind:
                with session_scope() as session:
                    job = session.get(ImportJob, job_id)
                    if job:
                        job.kind = detected_kind
                        job.source = detected
                        job.updated_at = now_iso()
                return run_import(job_id)
            raise ValueError("未知导入类型")

        if meta.get("pdf_url"):
            _progress(job_id, 46, "下载 PDF")
            tmp_pdf = PAPERS_DIR / f".incoming-{uuid.uuid4().hex}.pdf"
            if _download_pdf(meta["pdf_url"], tmp_pdf):
                upload_path = tmp_pdf

        with session_scope() as session:
            _progress(job_id, 62, "写入文献库与 Markdown 笔记")
            paper = persist_paper(session, meta, uploaded_pdf=upload_path)
            paper_id = paper.id
        _progress(job_id, 92, "建立 FTS5 索引")
        with session_scope() as session:
            paper = session.get(Paper, paper_id)
            if paper:
                index_paper(session, paper)
        _complete(job_id, paper_id)
    except Exception as exc:  # pragma: no cover - defensive worker boundary
        _fail(job_id, f"{type(exc).__name__}: {exc}")


def enqueue_import(source: str, kind: str = "auto") -> str:
    job_id = f"job-{uuid.uuid4().hex[:10]}"
    timestamp = now_iso()
    with session_scope() as session:
        session.add(
            ImportJob(
                id=job_id,
                source=source,
                kind=kind,
                status="queued",
                progress=0,
                message="已进入队列",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    thread = threading.Thread(target=run_import, args=(job_id,), daemon=True)
    thread.start()
    return job_id


def save_uploaded_pdf(data: bytes, filename: str) -> Path:
    target = ATTACHMENTS_DIR / f"upload-{uuid.uuid4().hex[:10]}-{Path(filename).name}"
    target.write_bytes(data)
    return target


def get_job(job_id: str) -> dict | None:
    with session_scope() as session:
        job = session.get(ImportJob, job_id)
        if not job:
            return None
        return {
            "id": job.id,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "paper_id": job.paper_id,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "kind": job.kind,
        }
