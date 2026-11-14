from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from markdown_it import MarkdownIt
from sqlalchemy import text
from sqlmodel import Session

from ..config import DATA_DIR, DRAFTS_DIR
from ..markdown import parse_markdown
from ..models import Draft, Paper, Run
from ..utils import write_text

CITE_RE = re.compile(r"\[@([A-Za-z0-9_:\-]+)\]")
RUN_RE = re.compile(r"\{\{run:([A-Za-z0-9-]+)(?:/([^}]+))?\}\}")


def _tool_env() -> dict[str, str]:
    """Give child tools a writable temp directory.

    The backend can be launched under a Windows low-integrity sandbox where
    %TEMP% is not writable. Pandoc extracts media into TMP, so point every
    relevant variable at the (writable) data directory.
    """
    tmp = DATA_DIR / ".tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({"TMP": str(tmp), "TEMP": str(tmp), "TMPDIR": str(tmp)})
    return env


def find_pandoc() -> str | None:
    candidates = [
        shutil.which("pandoc"),
        str(Path.home() / "AppData/Local/Pandoc/pandoc.exe"),
        r"C:\Program Files\Pandoc\pandoc.exe",
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


def find_tectonic() -> str | None:
    candidates = [
        shutil.which("tectonic"),
        str(Path.home() / ".local/bin/tectonic.exe"),
        str(Path.home() / "AppData/Local/Tectonic/tectonic.exe"),
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


def cjk_font() -> str:
    system = platform.system()
    if system == "Windows":
        return "Microsoft YaHei"
    if system == "Darwin":
        return "PingFang SC"
    return "Noto Sans CJK SC"


def tools_status() -> dict:
    return {
        "pandoc": find_pandoc(),
        "tectonic": find_tectonic(),
        "pdf_export": bool(find_pandoc() and find_tectonic()),
    }


def _collect_bib(session: Session, body: str) -> tuple[list[Paper], str]:
    keys = []
    for match in CITE_RE.finditer(body):
        if match.group(1) not in keys:
            keys.append(match.group(1))
    papers = []
    for key in keys:
        paper = session.execute(
            text("SELECT id FROM paper WHERE bibkey = :k"), {"k": key}
        ).first()
        if paper:
            item = session.get(Paper, paper[0])
            if item:
                papers.append(item)
    bib = "\n\n".join(p.bibtex or "" for p in papers if p.bibtex)
    return papers, bib


def _expand_run_placeholders(session: Session, body: str) -> str:
    def repl(match: re.Match) -> str:
        run_id, filename = match.group(1), match.group(2)
        run = session.get(Run, run_id)
        if not run:
            return f"> [缺失运行 {run_id}]"
        artifacts = session.execute(
            text("SELECT path, kind FROM artifact WHERE run_id = :rid"),
            {"rid": run_id},
        ).all()
        if not artifacts:
            return f"> [运行 {run_id} 暂无产物]"
        chosen = None
        for path, _kind in artifacts:
            if filename and Path(path).name == Path(filename).name:
                chosen = path
                break
        chosen = chosen or artifacts[0][0]
        return f"![{Path(chosen).stem}]({Path(chosen).as_posix()})"

    return RUN_RE.sub(repl, body)


def render_local_html(title: str, body: str, papers: list[Paper]) -> str:
    md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable("table")
    rendered = md.render(body)
    rendered = CITE_RE.sub(lambda m: f'<span class="citation">[{m.group(1)}]</span>', rendered)
    refs = "".join(
        f"<li>[{p.bibkey}] {p.title}. {', '.join(json.loads(p.authors or '[]')) if p.authors else ''} ({p.year or 'n.d.'}).</li>"
        for p in papers
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{ --ink:#1b1b18; --muted:#6d6a61; --accent:#c84b31; }}
  body {{ max-width: 760px; margin: 56px auto; padding: 0 28px; color:var(--ink);
         font-family: "Source Han Serif SC","Noto Serif SC",Georgia,serif; line-height:1.9; font-size:17px; }}
  h1 {{ font-size:2.1rem; line-height:1.3; margin-bottom:2rem; }}
  h2 {{ font-size:1.35rem; margin-top:2.4rem; border-bottom:1px solid #ddd8cc; padding-bottom:.35rem; }}
  h3 {{ font-size:1.1rem; }}
  p {{ margin: .85rem 0; }}
  blockquote {{ border-left:3px solid var(--accent); margin:1.4rem 0; padding:.3rem 1rem; color:var(--muted); background:#faf7f0; }}
  code {{ font-family: ui-monospace,monospace; background:#f0ece3; padding:.12rem .3rem; border-radius:3px; }}
  .citation {{ color:var(--accent); font-size:.92em; }}
  .refs {{ margin-top:3rem; border-top:1px solid #ddd8cc; padding-top:1rem; font-size:.9rem; color:var(--muted); }}
  .refs li {{ margin:.4rem 0; }}
  @media print {{ body {{ margin:0; }} }}
</style></head>
<body><article>{rendered}</article>
<section class="refs"><h2>参考文献</h2><ol>{refs or '<li>暂无引用</li>'}</ol></section>
</body></html>"""


def export_draft(session: Session, draft_id: str, fmt: str = "html") -> tuple[Path, str]:
    draft = session.get(Draft, draft_id)
    if not draft or not draft.path:
        raise ValueError("draft not found")
    source = Path(draft.path)
    if not source.exists():
        raise ValueError("draft markdown file missing")
    doc = parse_markdown(source)
    body = _expand_run_placeholders(session, doc.body)
    # The standalone pandoc template already renders the title from metadata.
    body = re.sub(r"^\s*#\s+[^\n]+\n+", "", body, count=1)
    papers, bib = _collect_bib(session, doc.body)
    draft_dir = DRAFTS_DIR / draft.id
    out_dir = draft_dir / ".exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    refs_path = draft_dir / "refs.bib"
    write_text(refs_path, bib or "% no references yet\n")
    work_md = out_dir / "main.expanded.md"
    write_text(work_md, body)

    pandoc = find_pandoc()
    if fmt == "html":
        target = out_dir / "preview.html"
        if pandoc:
            cmd = [
                pandoc,
                str(work_md),
                "-o",
                str(target),
                "--standalone",
                "--citeproc",
                "--bibliography",
                str(refs_path),
                "--mathml",
                "--metadata",
                f"title={draft.title}",
                "-c",
                "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, env=_tool_env()
            )
            if result.returncode == 0 and target.exists():
                return target, "html"
        html = render_local_html(draft.title, body, papers)
        write_text(target, html)
        return target, "html"

    if fmt == "md":
        return work_md, "md"

    if fmt == "tex":
        if not pandoc:
            raise RuntimeError("未安装 pandoc，无法生成 LaTeX。")
        target = out_dir / "main.tex"
        result = subprocess.run(
            [
                pandoc,
                str(work_md),
                "-o",
                str(target),
                "--standalone",
                "--citeproc",
                "--bibliography",
                str(refs_path),
                "--natbib",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=_tool_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(f"pandoc 失败：{result.stderr[-400:]}")
        return target, "tex"

    if fmt == "pdf":
        if not pandoc:
            raise RuntimeError("未安装 pandoc，无法导出 PDF。")
        tectonic = find_tectonic()
        if not tectonic:
            raise RuntimeError("未安装 tectonic，无法编译 PDF。请运行 scripts/install-tools.ps1。")
        target = out_dir / f"{draft.id}.pdf"
        result = subprocess.run(
            [
                pandoc,
                str(work_md),
                "-o",
                str(target),
                "--standalone",
                "--citeproc",
                "--bibliography",
                str(refs_path),
                "--pdf-engine",
                tectonic,
                "-V",
                "geometry:margin=2.4cm",
                "-V",
                "fontsize=11pt",
                "-V",
                f"CJKmainfont={cjk_font()}",
                "--metadata",
                f"title={draft.title}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            env=_tool_env(),
        )
        if result.returncode != 0:
            log = (result.stderr or "") + "\n" + (result.stdout or "")
            write_text(out_dir / "export.log", log)
            detail = log.strip()[-1800:] or "tectonic 未返回错误信息"
            raise RuntimeError(f"PDF 编译失败：\n{detail}")
        return target, "pdf"

    raise ValueError("unsupported format")
