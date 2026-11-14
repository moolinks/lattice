import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  Bot,
  Check,
  Copy,
  FileText,
  Highlighter,
  Loader2,
  MessageSquare,
  Plus,
  Save,
  Sparkles,
  Star,
  Trash2,
} from "lucide-react";
import { del, get, patch, post, put } from "@/lib/api";
import type { AskResponse, PaperDetail as PaperDetailType } from "@/lib/types";
import { authorsLine, formatDate, relativeTime, statusLabel } from "@/lib/format";
import { toast } from "@/lib/toast";
import { PageSkeleton, Spinner, EmptyState } from "@/components/Feedback";
import { StatusPill } from "@/components/StatusPill";
import { MarkdownEditor } from "@/components/MarkdownEditor";
import { Markdown } from "@/lib/markdown";

const STATUSES = ["unread", "reading", "read", "key", "archived"];

export function PaperDetail() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"note" | "pdf" | "chunks">("note");
  const [noteBody, setNoteBody] = useState("");
  const [dirty, setDirty] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [annotationOpen, setAnnotationOpen] = useState(false);
  const [annotation, setAnnotation] = useState({ page: 1, quote: "", comment: "" });

  const { data, isLoading, error } = useQuery({
    queryKey: ["paper", id],
    queryFn: () => get<PaperDetailType>(`/papers/${id}`),
    enabled: Boolean(id),
  });

  useEffect(() => {
    if (data) {
      setNoteBody(data.note.body);
      setDirty(false);
      setAnswer(null);
    }
  }, [data?.id]);

  const saveNote = useMutation({
    mutationFn: () => put(`/papers/${id}/note`, { body: noteBody }),
    onSuccess: () => {
      setDirty(false);
      toast("笔记已保存，索引同步完成。");
      queryClient.invalidateQueries({ queryKey: ["paper", id] });
      queryClient.invalidateQueries({ queryKey: ["papers"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err: Error) => toast(err.message, "error"),
  });

  const updatePaper = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch(`/papers/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["paper", id] });
      queryClient.invalidateQueries({ queryKey: ["papers"] });
      toast("文献状态已更新");
    },
    onError: (err: Error) => toast(err.message, "error"),
  });

  const ask = useMutation({
    mutationFn: () => post<AskResponse>(`/papers/${id}/ask`, { question }),
    onSuccess: (response) => setAnswer(response),
    onError: (err: Error) => toast(err.message, "error"),
  });

  const summarize = useMutation({
    mutationFn: () =>
      post<{ summary: string; mode: string; model?: string | null; record_id: number }>(
        `/papers/${id}/summarize`,
      ),
    onSuccess: (result) => {
      toast(
        result.mode === "anthropic"
          ? "摘要已生成"
          : "本地证据摘要已生成；配置 API Key 可启用 LLM 综合",
      );
      queryClient.invalidateQueries({ queryKey: ["paper", id] });
    },
    onError: (err: Error) => toast(err.message, "error"),
  });

  const addAnnotation = useMutation({
    mutationFn: () => post(`/papers/${id}/annotations`, annotation),
    onSuccess: () => {
      toast("批注已添加");
      setAnnotation({ page: annotation.page, quote: "", comment: "" });
      setAnnotationOpen(false);
      queryClient.invalidateQueries({ queryKey: ["paper", id] });
    },
    onError: (err: Error) => toast(err.message, "error"),
  });

  const removeAnnotation = useMutation({
    mutationFn: (annotationId: number) => del(`/papers/${id}/annotations/${annotationId}`),
    onSuccess: () => {
      toast("批注已删除");
      queryClient.invalidateQueries({ queryKey: ["paper", id] });
    },
    onError: (err: Error) => toast(err.message, "error"),
  });

  const { data: chunks, isFetching: chunksLoading } = useQuery({
    queryKey: ["chunks", id],
    queryFn: () => get<{ items: { id: string; page: number; text: string }[] }>(`/papers/${id}/chunks?limit=60`),
    enabled: tab === "chunks",
  });

  const outline = useMemo(() => {
    const headings = noteBody.match(/^#{1,3} .+$/gm) ?? [];
    return headings.map((heading) => ({
      level: heading.match(/^#+/)?.[0].length ?? 1,
      text: heading.replace(/^#+\s*/, ""),
    }));
  }, [noteBody]);

  if (isLoading) return <PageSkeleton />;
  if (error || !data) {
    return (
      <div className="page">
        <EmptyState
          icon={<BookOpen size={30} />}
          title="没有找到这篇文献"
          description={(error as Error)?.message ?? "它可能已被删除。"}
          action={<Link to="/papers" className="btn btn-primary">返回文献库</Link>}
        />
      </div>
    );
  }

  return (
    <div className="page paper-detail-page">
      <div className="detail-back-row">
        <Link to="/papers" className="back-link"><ArrowLeft size={14} /> 文献库</Link>
        <span className="crumb-sep">/</span>
        <span>{data.id}</span>
        {dirty && <span className="unsaved-dot">未保存</span>}
      </div>

      <header className="paper-hero">
        <div className="paper-hero-main">
          <div className="paper-hero-tags">
            <StatusPill status={data.status} />
            {data.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
            {data.arxiv_id && <span className="tag tag-mono">arXiv:{data.arxiv_id}</span>}
          </div>
          <h1>{data.title}</h1>
          <p className="paper-authors">{authorsLine(data.authors, 8)}</p>
          <div className="paper-venue-line">
            <span>{data.year ?? "—"}</span>
            <span className="dot-sep" />
            <span>{data.venue || "—"}</span>
            {data.doi && (
              <>
                <span className="dot-sep" />
                <a href={`https://doi.org/${data.doi}`} target="_blank" rel="noreferrer">
                  DOI <ArrowUpRight size={11} />
                </a>
              </>
            )}
          </div>
        </div>
        <div className="paper-hero-actions">
          <div className="rating" title="评分">
            {[1, 2, 3, 4, 5].map((value) => (
              <button
                key={value}
                className={value <= (data.rating ?? 0) ? "active" : ""}
                onClick={() => updatePaper.mutate({ rating: value === data.rating ? null : value })}
                aria-label={`评分 ${value}`}
              >
                <Star size={15} fill={value <= (data.rating ?? 0) ? "currentColor" : "none"} />
              </button>
            ))}
          </div>
          <select
            className="status-select"
            value={data.status}
            onChange={(event) => updatePaper.mutate({ status: event.target.value })}
          >
            {STATUSES.map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}
          </select>
          {data.pdf_url && (
            <a className="btn btn-ghost" href={data.pdf_url} target="_blank" rel="noreferrer">
              <FileText size={14} /> PDF
            </a>
          )}
          {data.url && (
            <a className="btn btn-ghost" href={data.url} target="_blank" rel="noreferrer">
              arXiv <ArrowUpRight size={13} />
            </a>
          )}
        </div>
      </header>

      <div className="paper-layout">
        <div className="paper-main-col">
          <section className="panel abstract-panel">
            <div className="section-eyebrow">ABSTRACT</div>
            <p>{data.abstract || "暂无摘要。"}</p>
            <div className="abstract-footer">
              <span>{data.chunks_count} 个全文分块</span>
              <span>{data.annotation_count} 条批注</span>
              <span>创建于 {formatDate(data.created_at)}</span>
            </div>
          </section>

          <div className="editor-panel panel">
            <div className="editor-tabs-row">
              <div className="editor-tabs">
                <button className={tab === "note" ? "active" : ""} onClick={() => setTab("note")}>
                  <BookOpen size={14} /> Markdown 笔记
                </button>
                <button className={tab === "pdf" ? "active" : ""} onClick={() => setTab("pdf")}>
                  <FileText size={14} /> PDF 原文
                </button>
                <button className={tab === "chunks" ? "active" : ""} onClick={() => setTab("chunks")}>
                  <MessageSquare size={14} /> 全文章节
                </button>
              </div>
              <div className="editor-actions">
                {tab === "note" && (
                  <button className="btn btn-primary btn-sm" onClick={() => saveNote.mutate()} disabled={!dirty || saveNote.isPending}>
                    {saveNote.isPending ? <Loader2 size={13} className="spin" /> : <Save size={13} />}
                    {saveNote.isPending ? "保存中" : "保存"}
                  </button>
                )}
              </div>
            </div>

            {tab === "note" && (
              <div className="note-editor-wrap">
                <div className="note-outline">
                  <span className="outline-label">OUTLINE</span>
                  {outline.slice(0, 12).map((item, index) => (
                    <button
                      key={`${item.text}-${index}`}
                      className={`outline-item level-${item.level}`}
                      onClick={() => setTab("note")}
                    >
                      {item.text}
                    </button>
                  ))}
                  {!outline.length && <span className="small muted">笔记还没有标题。</span>}
                </div>
                <MarkdownEditor
                  value={noteBody}
                  onChange={(value) => {
                    setNoteBody(value);
                    setDirty(true);
                  }}
                  onSave={() => saveNote.mutate()}
                  height="620px"
                />
              </div>
            )}

            {tab === "pdf" && (
              <div className="pdf-frame-wrap">
                {data.pdf_url ? (
                  <iframe src={`${data.pdf_url}#page=${data.annotations[0]?.page ?? 1}`} title={`${data.title} PDF`} />
                ) : (
                  <EmptyState
                    icon={<FileText size={28} />}
                    title="没有本地 PDF"
                    description="这篇文献只有元数据。重新导入 PDF 或通过 arXiv 链接补全。"
                  />
                )}
              </div>
            )}

            {tab === "chunks" && (
              <div className="chunk-list">
                {chunksLoading && <div className="loading-inline"><Spinner /> 读取分块…</div>}
                {chunks?.items.map((chunk) => (
                  <article className="chunk-card" key={chunk.id}>
                    <div className="chunk-head">
                      <span>{chunk.id}</span>
                      <span>p.{chunk.page}</span>
                    </div>
                    <p>{chunk.text}</p>
                  </article>
                ))}
                {!chunksLoading && !chunks?.items.length && (
                  <EmptyState compact title="还没有全文分块" description="导入带 PDF 的文献后会自动生成。" />
                )}
              </div>
            )}
          </div>
        </div>

        <aside className="paper-side-col">
          <section className="panel ai-panel">
            <div className="ai-panel-head">
              <span className="ai-orb"><Bot size={16} /></span>
              <div>
                <strong>研究助手</strong>
                <span>BM25 召回 + 页码引用</span>
              </div>
              <button
                className="icon-button"
                onClick={() => summarize.mutate()}
                title="生成结构化摘要"
                disabled={summarize.isPending}
              >
                {summarize.isPending ? <Loader2 size={14} className="spin" /> : <Sparkles size={15} />}
              </button>
            </div>
            {data.ai_summary && (
              <div className="ai-summary">
                <div className="ai-summary-meta">
                  <span className={`ai-mode ai-mode-${data.latest_summary?.mode ?? "local"}`}>
                    {data.latest_summary?.mode ?? "summary"}
                  </span>
                  {data.latest_summary?.model && <span>{data.latest_summary.model}</span>}
                  <span>{data.latest_summary?.evidence.length ?? 0} 条页码证据</span>
                  <button className="icon-button" onClick={() => summarize.mutate()} title="重新生成摘要">
                    {summarize.isPending ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />}
                  </button>
                </div>
                <Markdown compact>{data.ai_summary}</Markdown>
                {!!data.latest_summary?.evidence.length && (
                  <details className="summary-evidence">
                    <summary>查看证据链</summary>
                    {data.latest_summary.evidence.slice(0, 6).map((item) => (
                      <button
                        key={`${item.chunk_id}-${item.role}-${item.page}`}
                        onClick={() => {
                          setTab("pdf");
                          window.setTimeout(() => {
                            const frame = document.querySelector<HTMLIFrameElement>(".pdf-frame-wrap iframe");
                            if (frame) frame.src = `${data.pdf_url}#page=${item.page ?? 1}`;
                          }, 30);
                        }}
                      >
                        <span>{item.role} · {item.page ? `p.${item.page}` : "abstract"}</span>
                        {item.quote}
                      </button>
                    ))}
                  </details>
                )}
              </div>
            )}
            <div className="ai-ask">
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="针对这篇论文提问，例如：它的语义 ID 是按什么目标学习的？"
                rows={3}
                onKeyDown={(event) => {
                  if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && question.trim()) {
                    ask.mutate();
                  }
                }}
              />
              <button className="btn btn-primary btn-sm" onClick={() => ask.mutate()} disabled={!question.trim() || ask.isPending}>
                {ask.isPending ? <Loader2 size={13} className="spin" /> : <MessageSquare size={13} />}
                提问
              </button>
            </div>
            {answer && (
              <div className="ai-answer">
                <div className="ai-answer-meta">
                  <span className={`ai-mode ai-mode-${answer.mode}`}>{answer.mode}</span>
                  {answer.model && <span>{answer.model}</span>}
                </div>
                <Markdown compact>{answer.answer}</Markdown>
                {answer.citations.length > 0 && (
                  <div className="citation-list">
                    <span className="citation-label">定位证据</span>
                    {answer.citations.slice(0, 4).map((citation) => (
                      <button
                        key={citation.chunk_id}
                        onClick={() => {
                          setTab("pdf");
                          window.setTimeout(() => {
                            const frame = document.querySelector<HTMLIFrameElement>(".pdf-frame-wrap iframe");
                            if (frame) frame.src = `${data.pdf_url}#page=${citation.page ?? 1}`;
                          }, 30);
                        }}
                      >
                        p.{citation.page ?? "?"} · {citation.text.slice(0, 50)}…
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {!data.ai_summary && !answer && (
              <p className="ai-hint">
                未配置 API Key 时，系统返回 BM25 定位到的原文证据，不会伪造模型答案。
              </p>
            )}
          </section>

          <section className="panel meta-panel">
            <div className="side-panel-head">
              <h3>元数据</h3>
              <button
                className="icon-button"
                title="复制 bibkey"
                onClick={() => {
                  if (data.bibkey) {
                    navigator.clipboard.writeText(data.bibkey);
                    toast(`已复制 ${data.bibkey}`);
                  }
                }}
              >
                <Copy size={14} />
              </button>
            </div>
            <dl className="meta-list">
              <div><dt>ID</dt><dd>{data.id}</dd></div>
              <div><dt>Bibkey</dt><dd className="mono">{data.bibkey ?? "—"}</dd></div>
              <div><dt>状态</dt><dd>{statusLabel(data.status)}</dd></div>
              <div><dt>更新</dt><dd>{relativeTime(data.updated_at)}</dd></div>
              <div><dt>笔记文件</dt><dd className="mono path-value">{data.note_path?.split("\\").pop() ?? "—"}</dd></div>
            </dl>
          </section>

          <section className="panel annotation-panel">
            <div className="side-panel-head">
              <h3>批注 <span className="count-chip">{data.annotations.length}</span></h3>
              <button className="icon-button" onClick={() => setAnnotationOpen((value) => !value)}>
                <Plus size={15} />
              </button>
            </div>
            {annotationOpen && (
              <div className="annotation-form">
                <div className="annotation-form-row">
                  <label>
                    页码
                    <input
                      type="number"
                      min={1}
                      value={annotation.page}
                      onChange={(event) => setAnnotation({ ...annotation, page: Number(event.target.value) })}
                    />
                  </label>
                </div>
                <textarea
                  placeholder="原文摘录…"
                  value={annotation.quote}
                  onChange={(event) => setAnnotation({ ...annotation, quote: event.target.value })}
                  rows={2}
                />
                <textarea
                  placeholder="你的评论 / 疑问…"
                  value={annotation.comment}
                  onChange={(event) => setAnnotation({ ...annotation, comment: event.target.value })}
                  rows={2}
                />
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => addAnnotation.mutate()}
                  disabled={(!annotation.quote && !annotation.comment) || addAnnotation.isPending}
                >
                  <Check size={13} /> 保存批注
                </button>
              </div>
            )}
            <div className="annotation-list">
              {data.annotations.map((item) => (
                <article className="annotation-item" key={item.id}>
                  <div className="annotation-top">
                    <span>p.{item.page ?? "—"}</span>
                    <button className="icon-button" onClick={() => removeAnnotation.mutate(item.id)}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                  {item.quote && <blockquote>{item.quote}</blockquote>}
                  {item.comment && <p>{item.comment}</p>}
                </article>
              ))}
              {!data.annotations.length && (
                <p className="small muted annotation-empty"><Highlighter size={13} /> 还没有批注。手动记录摘录与评论。</p>
              )}
            </div>
          </section>

          <section className="panel related-panel">
            <div className="side-panel-head"><h3>关联实体</h3></div>
            {data.related.length ? (
              <div className="related-list">
                {data.related.map((item) => (
                  <Link to={item.type === "paper" ? `/papers/${item.id}` : item.type === "experiment" ? `/experiments/${item.id}` : item.type === "draft" ? `/drafts/${item.id}` : `/ideas?focus=${item.id}`} key={`${item.id}-${item.relation}`}>
                    <span className="related-type">{item.type}</span>
                    <span>{item.title}</span>
                    <ArrowUpRight size={12} />
                  </Link>
                ))}
              </div>
            ) : (
              <p className="small muted">在笔记中写 [[P0001]]、[[I0001]] 或 [@bibkey] 建立关系。</p>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
