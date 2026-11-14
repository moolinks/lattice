import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BookOpen,
  Check,
  FileUp,
  Filter,
  Link2,
  Loader2,
  Plus,
  Search,
  X,
} from "lucide-react";
import { get, post, qs, upload } from "@/lib/api";
import type { ImportJob, Paper } from "@/lib/types";
import { formatDate, relativeTime, statusLabel, truncate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { PageSkeleton } from "@/components/Feedback";
import { StatusPill } from "@/components/StatusPill";
import { Modal } from "@/components/Modal";

interface PaperListResponse {
  items: Paper[];
  total: number;
  status_counts: Record<string, number>;
  tags: string[];
}

const STATUS_TABS = ["all", "unread", "reading", "read", "key", "archived"];

export function Library() {
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [tag, setTag] = useState("");
  const [sort, setSort] = useState("updated");
  const [importOpen, setImportOpen] = useState(false);
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(q.trim()), 220);
    return () => window.clearTimeout(timer);
  }, [q]);

  const { data, isLoading } = useQuery({
    queryKey: ["papers", status, debounced, tag, sort],
    queryFn: () =>
      get<PaperListResponse>(
        `/papers${qs({ status, q: debounced, tag, sort, limit: 100 })}`,
      ),
  });

  const counts = data?.status_counts ?? {};
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);

  return (
    <div className="page library-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" />LITERATURE INDEX</div>
          <h1>文献库</h1>
          <p>
            {total} 篇文献，SQLite 存结构化元数据，PDF 与 Markdown 笔记独立保存。
            {data?.total !== undefined && data.total !== total && ` 当前筛选 ${data.total} 篇。`}
          </p>
        </div>
        <div className="heading-actions">
          <button className="btn btn-primary" onClick={() => setImportOpen(true)}>
            <Plus size={15} /> 导入文献
          </button>
        </div>
      </div>

      <div className="library-toolbar panel">
        <div className="status-tabs">
          {STATUS_TABS.map((value) => (
            <button
              key={value}
              className={status === value ? "active" : ""}
              onClick={() => setStatus(value)}
            >
              {statusLabel(value)}
              <span>{value === "all" ? total : counts[value] ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="toolbar-row">
          <label className="search-field">
            <Search size={15} />
            <input
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder="按标题、作者、摘要筛选…"
            />
            {q && (
              <button className="icon-button" onClick={() => setQ("")} aria-label="清空">
                <X size={13} />
              </button>
            )}
          </label>
          <label className="select-field">
            <Filter size={14} />
            <select value={tag} onChange={(event) => setTag(event.target.value)}>
              <option value="">全部标签</option>
              {data?.tags.map((item) => (
                <option value={item} key={item}>{item}</option>
              ))}
            </select>
          </label>
          <label className="select-field">
            <select value={sort} onChange={(event) => setSort(event.target.value)}>
              <option value="updated">最近更新</option>
              <option value="year">年份</option>
              <option value="rating">评分</option>
              <option value="title">标题</option>
            </select>
          </label>
        </div>
      </div>

      {isLoading ? (
        <PageSkeleton />
      ) : (
        <div className="paper-table panel">
          <div className="paper-table-head">
            <span>文献</span>
            <span>标签</span>
            <span>状态</span>
            <span>更新</span>
            <span />
          </div>
          {data?.items.map((paper) => (
            <Link to={`/papers/${paper.id}`} className="paper-table-row" key={paper.id}>
              <div className="paper-cell-main">
                <div className="paper-cell-top">
                  <span className="paper-id">{paper.id}</span>
                  {paper.has_pdf && <span className="mini-badge">PDF</span>}
                  {paper.annotation_count > 0 && (
                    <span className="mini-badge annotation">{paper.annotation_count} 批注</span>
                  )}
                </div>
                <h3>{paper.title}</h3>
                <p className="paper-cell-meta">
                  {paper.authors.slice(0, 3).join(", ")}
                  {paper.authors.length > 3 ? " et al." : ""}
                  <span>·</span> {paper.year ?? "—"} <span>·</span> {paper.venue || "—"}
                </p>
                {paper.note_excerpt && (
                  <p className="paper-note-excerpt">{truncate(paper.note_excerpt, 120)}</p>
                )}
              </div>
              <div className="paper-cell-tags">
                {paper.tags.slice(0, 3).map((item) => (
                  <span className="tag" key={item}>{item}</span>
                ))}
              </div>
              <div><StatusPill status={paper.status} /></div>
              <div className="paper-updated">
                <span>{relativeTime(paper.updated_at)}</span>
                <small>{formatDate(paper.created_at)}</small>
              </div>
              <ArrowUpRight size={15} className="row-arrow" />
            </Link>
          ))}
          {!data?.items.length && (
            <div className="table-empty">
              <BookOpen size={28} strokeWidth={1.2} />
              <strong>没有匹配的文献</strong>
              <p>清空筛选，或导入一篇 arXiv 论文开始。</p>
              <button className="btn btn-primary" onClick={() => setImportOpen(true)}>
                <Plus size={15} /> 导入第一篇
              </button>
            </div>
          )}
        </div>
      )}

      <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} />
    </div>
  );
}

type ImportMode = "arxiv" | "pdf" | "bibtex";

function ImportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [mode, setMode] = useState<ImportMode>("arxiv");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!open) {
      setSource("");
      setFile(null);
      setJobId(null);
      setMode("arxiv");
    }
  }, [open]);

  const start = useMutation({
    mutationFn: async () => {
      if (mode === "pdf") {
        if (!file) throw new Error("请先选择一个 PDF 文件");
        return upload<{ job_id: string }>("/papers/upload", file);
      }
      if (!source.trim()) throw new Error("请输入 arXiv ID、DOI 或 BibTeX");
      return post<{ job_id: string }>("/papers/import", {
        source: source.trim(),
        kind: mode === "bibtex" ? "bibtex" : "auto",
      });
    },
    onSuccess: (response) => {
      setJobId(response.job_id);
      toast("已开始导入，正在建立全文索引。", "info");
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const { data: job } = useQuery({
    queryKey: ["import-job", jobId],
    queryFn: () => get<ImportJob>(`/papers/imports/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const current = query.state.data;
      return current && ["complete", "failed"].includes(current.status) ? false : 900;
    },
  });

  useEffect(() => {
    if (!job) return;
    if (job.status === "complete") {
      toast("文献导入完成，全文索引已就绪。");
      queryClient.invalidateQueries({ queryKey: ["papers"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      if (job.paper_id) {
        window.setTimeout(() => {
          onClose();
          navigate(`/papers/${job.paper_id}`);
        }, 700);
      }
    }
    if (job.status === "failed") {
      toast(job.message || "导入失败", "error");
    }
  }, [job, navigate, onClose, queryClient]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="导入文献"
      subtitle="arXiv / DOI / PDF / BibTeX → 元数据、全文分块、Markdown 笔记与 FTS5 索引"
      width="lg"
    >
      {!jobId ? (
        <>
          <div className="import-tabs">
            <button className={mode === "arxiv" ? "active" : ""} onClick={() => setMode("arxiv")}>
              <Link2 size={15} /> arXiv / DOI
            </button>
            <button className={mode === "pdf" ? "active" : ""} onClick={() => setMode("pdf")}>
              <FileUp size={15} /> 本地 PDF
            </button>
            <button className={mode === "bibtex" ? "active" : ""} onClick={() => setMode("bibtex")}>
              <BookOpen size={15} /> BibTeX
            </button>
          </div>

          {mode === "arxiv" && (
            <div className="import-form">
              <label className="form-label" htmlFor="source">论文标识或链接</label>
              <input
                id="source"
                className="text-input"
                value={source}
                onChange={(event) => setSource(event.target.value)}
                placeholder="2305.05065 或 https://arxiv.org/abs/2412.15579 或 10.1145/…"
                autoFocus
              />
              <p className="form-hint">
                系统会请求 arXiv / Crossref 补全元数据，并尝试下载公开 PDF。请求间隔遵守 3 秒限流。
              </p>
              <div className="example-chips">
                {["2305.05065", "2412.15579", "2304.03516"].map((example) => (
                  <button key={example} onClick={() => setSource(example)}>
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}

          {mode === "pdf" && (
            <div
              className={`drop-zone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                const dropped = event.dataTransfer.files?.[0];
                if (dropped?.name.toLowerCase().endsWith(".pdf")) setFile(dropped);
                else toast("只接受 PDF 文件", "error");
              }}
              onClick={() => fileRef.current?.click()}
            >
              <input
                ref={fileRef}
                type="file"
                accept="application/pdf"
                hidden
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              {file ? (
                <>
                  <FileUp size={28} />
                  <strong>{file.name}</strong>
                  <span>{(file.size / 1024 / 1024).toFixed(2)} MB · 点击重新选择</span>
                </>
              ) : (
                <>
                  <FileUp size={28} />
                  <strong>拖入 PDF，或点击选择文件</strong>
                  <span>最大 80 MB。PyMuPDF 抽取文本后按页切块。</span>
                </>
              )}
            </div>
          )}

          {mode === "bibtex" && (
            <div className="import-form">
              <label className="form-label" htmlFor="bibtex">BibTeX 条目</label>
              <textarea
                id="bibtex"
                className="code-textarea"
                value={source}
                onChange={(event) => setSource(event.target.value)}
                rows={10}
                placeholder={"@article{key,\n  title = {…},\n  author = {…},\n  year = {2025}\n}"}
              />
              <p className="form-hint">会优先尝试用条目中的 DOI / arXiv ID 补全全文。</p>
            </div>
          )}

          <div className="import-footer">
            <span className="small muted">
              导入在后台线程执行，不阻塞阅读与搜索。
            </span>
            <button
              className="btn btn-primary"
              onClick={() => start.mutate()}
              disabled={start.isPending}
            >
              {start.isPending ? <Loader2 size={15} className="spin" /> : <Plus size={15} />}
              {start.isPending ? "开始导入…" : "开始导入"}
            </button>
          </div>
        </>
      ) : (
        <div className="import-progress">
          <div className={`import-progress-icon ${job?.status ?? "running"}`}>
            {job?.status === "complete" ? <Check size={26} /> : <Loader2 size={26} className="spin" />}
          </div>
          <h3>{job?.status === "complete" ? "导入完成" : job?.status === "failed" ? "导入失败" : "正在建立索引"}</h3>
          <p>{job?.message ?? "等待后台任务…"}</p>
          <div className="progress-track">
            <div style={{ width: `${job?.progress ?? 0}%` }} />
          </div>
          <div className="progress-meta">
            <span>{job?.progress ?? 0}%</span>
            <span>{job?.kind ?? ""}</span>
          </div>
          {job?.status === "failed" && (
            <button className="btn btn-ghost" onClick={() => setJobId(null)}>
              返回重试
            </button>
          )}
        </div>
      )}
    </Modal>
  );
}
