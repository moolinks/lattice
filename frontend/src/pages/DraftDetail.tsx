import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { EditorView } from "@codemirror/view";
import {
  ArrowLeft,
  ArrowUpRight,
  Download,
  FileDown,
  FileText,
  Loader2,
  Quote,
  Save,
  Sparkles,
} from "lucide-react";
import { get, patch, put, qs } from "@/lib/api";
import type { Draft, Paper } from "@/lib/types";
import { relativeTime, statusLabel } from "@/lib/format";
import { toast } from "@/lib/toast";
import { PageSkeleton, EmptyState, Spinner } from "@/components/Feedback";
import { StatusPill } from "@/components/StatusPill";
import { MarkdownEditor } from "@/components/MarkdownEditor";
import { Markdown } from "@/lib/markdown";
import { Modal } from "@/components/Modal";

export function DraftDetail() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const editorRef = useRef<EditorView | null>(null);
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("");
  const [dirty, setDirty] = useState(false);
  const [citationOpen, setCitationOpen] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);

  const { data: draft, isLoading } = useQuery({
    queryKey: ["draft", id],
    queryFn: () => get<Draft>(`/drafts/${id}`),
    enabled: Boolean(id),
  });

  useEffect(() => {
    if (draft) {
      setBody(draft.body ?? "");
      setTitle(draft.title);
      setDirty(false);
    }
  }, [draft?.id]);

  const save = useMutation({
    mutationFn: () => put(`/drafts/${id}`, { body, title }),
    onSuccess: () => {
      setDirty(false);
      toast("草稿已保存，引用关系已同步。");
      queryClient.invalidateQueries({ queryKey: ["draft", id] });
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const update = useMutation({
    mutationFn: (payload: Record<string, unknown>) => patch(`/drafts/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["draft", id] });
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const outline = useMemo(() => {
    return (body.match(/^#{1,4} .+$/gm) ?? []).map((heading) => ({
      level: heading.match(/^#+/)?.[0].length ?? 1,
      text: heading.replace(/^#+\s*/, ""),
    }));
  }, [body]);

  const cited = useMemo(() => {
    return draft?.related.filter((item) => item.type === "paper") ?? [];
  }, [draft]);

  async function exportDraft(format: "pdf" | "html" | "tex") {
    setExporting(format);
    try {
      const response = await fetch(`/api/drafts/${id}/export${qs({ format })}`);
      if (!response.ok) {
        let message = "导出失败";
        try {
          const payload = (await response.json()) as { detail?: string };
          message = payload.detail ?? message;
        } catch {
          // ignore
        }
        throw new Error(message);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${id}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast(`已导出 ${format.toUpperCase()}`);
    } catch (error) {
      toast((error as Error).message, "error");
    } finally {
      setExporting(null);
    }
  }

  function insertCitation(paper: Paper) {
    const text = `[@${paper.bibkey}]`;
    const view = editorRef.current;
    if (view) {
      view.dispatch(view.state.replaceSelection(text));
      view.focus();
    } else {
      setBody((current) => `${current} ${text}`);
    }
    setDirty(true);
    setCitationOpen(false);
  }

  if (isLoading) return <PageSkeleton />;
  if (!draft) {
    return <div className="page"><EmptyState title="没有找到这份草稿" action={<Link to="/drafts" className="btn btn-primary">返回写作台</Link>} /></div>;
  }

  return (
    <div className="page draft-detail-page">
      <div className="detail-back-row">
        <Link to="/drafts" className="back-link"><ArrowLeft size={14} /> 写作台</Link>
        <span className="crumb-sep">/</span>
        <span>{draft.id}</span>
        {dirty && <span className="unsaved-dot">未保存</span>}
      </div>

      <header className="draft-hero">
        <div className="draft-title-area">
          <div className="paper-hero-tags">
            <StatusPill status={draft.status} />
            <span className="tag">{draft.venue || "未指定 venue"}</span>
            <span className="small muted">{draft.word_count.toLocaleString()} 字 · {draft.citation_count} 处引用</span>
          </div>
          <input
            className="draft-title-input"
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              setDirty(true);
            }}
          />
        </div>
        <div className="draft-actions">
          <select
            className="status-select"
            value={draft.status}
            onChange={(event) => update.mutate({ status: event.target.value })}
          >
            {["outline", "writing", "review", "done"].map((status) => (
              <option value={status} key={status}>{statusLabel(status)}</option>
            ))}
          </select>
          <button className="btn btn-ghost btn-sm" onClick={() => setCitationOpen(true)}>
            <Quote size={13} /> 插入引用
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => exportDraft("html")} disabled={exporting !== null}>
            {exporting === "html" ? <Loader2 size={13} className="spin" /> : <Download size={13} />} HTML
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => exportDraft("pdf")} disabled={exporting !== null}>
            {exporting === "pdf" ? <Loader2 size={13} className="spin" /> : <FileDown size={13} />} PDF
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
            {save.isPending ? <Loader2 size={13} className="spin" /> : <Save size={13} />} 保存
          </button>
        </div>
      </header>

      <div className="draft-layout">
        <aside className="draft-outline panel">
          <span className="panel-kicker">OUTLINE</span>
          <div className="draft-outline-list">
            {outline.map((item, index) => (
              <button key={`${item.text}-${index}`} className={`outline-item level-${item.level}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                {item.text}
              </button>
            ))}
            {!outline.length && <p className="small muted">标题会出现在这里。</p>}
          </div>
          <div className="draft-outline-footer">
            <span className="panel-kicker">CITED</span>
            {cited.map((item) => <span className="tag" key={item.id}>{item.id}</span>)}
            {!cited.length && <span className="small muted">还没有引用。</span>}
          </div>
          <div className="draft-file-info">
            <FileText size={13} />
            <span>{draft.path?.split("\\").slice(-2).join("/")}</span>
          </div>
        </aside>

        <section className="draft-editor-col panel">
          <div className="draft-editor-head">
            <span><Sparkles size={13} /> Markdown 源文件</span>
            <span className="small muted">{dirty ? "有未保存修改" : `已保存 ${relativeTime(draft.updated_at)}`}</span>
          </div>
          <MarkdownEditor
            value={body}
            onChange={(value) => {
              setBody(value);
              setDirty(true);
            }}
            onSave={() => save.mutate()}
            height="calc(100vh - 260px)"
            editorRef={editorRef}
          />
        </section>

        <section className="draft-preview-col panel">
          <div className="draft-preview-head">
            <span className="panel-kicker">LIVE PREVIEW</span>
            <span className="small muted">KaTeX · GFM</span>
          </div>
          <div className="draft-preview-scroll">
            <Markdown>{body}</Markdown>
          </div>
        </section>
      </div>

      <CitationPicker open={citationOpen} onClose={() => setCitationOpen(false)} onPick={insertCitation} />
    </div>
  );
}

function CitationPicker({
  open,
  onClose,
  onPick,
}: {
  open: boolean;
  onClose: () => void;
  onPick: (paper: Paper) => void;
}) {
  const [q, setQ] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["papers", "citation-picker"],
    queryFn: () => get<{ items: Paper[] }>("/papers?limit=100"),
    enabled: open,
  });
  useEffect(() => {
    if (!open) setQ("");
  }, [open]);

  const items = (data?.items ?? []).filter((paper) => {
    const haystack = `${paper.title} ${paper.authors.join(" ")} ${paper.tags.join(" ")}`.toLowerCase();
    return haystack.includes(q.toLowerCase());
  });

  return (
    <Modal open={open} onClose={onClose} title="插入引用" subtitle="选择文献，插入 [@bibkey]，保存时自动同步 cites 关系。" width="md">
      <input className="text-input" value={q} onChange={(event) => setQ(event.target.value)} placeholder="搜索标题、作者、标签…" autoFocus />
      <div className="citation-picker-list">
        {isLoading && <div className="loading-inline"><Spinner /> 载入文献…</div>}
        {items.map((paper) => (
          <button className="citation-picker-row" key={paper.id} onClick={() => onPick(paper)}>
            <div>
              <strong>{paper.title}</strong>
              <span>{paper.authors.slice(0, 2).join(", ")} · {paper.year ?? "—"}</span>
            </div>
            <code>{paper.bibkey}</code>
            <ArrowUpRight size={13} />
          </button>
        ))}
        {!isLoading && !items.length && <p className="small muted">没有匹配文献。</p>}
      </div>
    </Modal>
  );
}
