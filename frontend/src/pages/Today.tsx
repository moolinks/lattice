import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  FlaskConical,
  Inbox,
  Lightbulb,
  PenLine,
  Plus,
  Quote,
  Sparkles,
} from "lucide-react";
import { get, patch, post } from "@/lib/api";
import type { Dashboard } from "@/lib/types";
import { relativeTime, statusLabel, truncate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { PageSkeleton, Spinner } from "@/components/Feedback";
import { ActivityBars } from "@/components/Charts";
import { StatusPill } from "@/components/StatusPill";

export function Today() {
  const queryClient = useQueryClient();
  const [inboxDraft, setInboxDraft] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => get<Dashboard>("/dashboard"),
  });

  const capture = useMutation({
    mutationFn: (content: string) => post("/inbox", { content }),
    onSuccess: () => {
      setInboxDraft("");
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast("已收进 Inbox");
    },
    onError: (err: Error) => toast(err.message, "error"),
  });

  const process = useMutation({
    mutationFn: (id: number) => patch(`/inbox/${id}?processed=true`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
  });

  if (isLoading) return <PageSkeleton />;
  if (error || !data) return <div className="page"><div className="error-panel">{(error as Error)?.message ?? "无法加载今日页"}</div></div>;

  const totalWords = data.drafts.reduce((sum, draft) => sum + draft.word_count, 0);
  const ideaTotal = Object.values(data.idea_counts).reduce((sum, value) => sum + value, 0);
  const continueDraft = data.drafts[0];

  return (
    <div className="page today-page">
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="eyebrow-line" />
            {data.today} · 星期{data.weekday}
          </div>
          <h1 className="hero-title">
            {data.greeting}，<em>研究者</em>。
          </h1>
          <p className="hero-sub">
            今天把「{data.focus.field}」的一个假设，向「{data.focus.subfield}」的真实问题再推进一步。
          </p>
          <div className="hero-actions">
            {continueDraft ? (
              <Link className="btn btn-primary" to={`/drafts/${continueDraft.id}`}>
                <PenLine size={15} /> 继续写 {continueDraft.id}
                <ArrowRight size={14} />
              </Link>
            ) : (
              <Link className="btn btn-primary" to="/papers">
                <BookOpen size={15} /> 开始读文献
              </Link>
            )}
            <Link className="btn btn-ghost" to="/ideas">
              <Lightbulb size={15} /> 打开思路板
            </Link>
          </div>
        </div>
        <div className="hero-coordinates">
          <div className="coord-head">
            <span>RESEARCH COORDINATES</span>
            <span className="coord-pulse" />
          </div>
          <div className="coord-field">{data.focus.field}</div>
          <div className="coord-sub">↳ {data.focus.subfield}</div>
          <div className="coord-questions">
            {data.focus.questions.slice(0, 2).map((question, index) => (
              <p key={question}>
                <span>0{index + 1}</span>
                {question}
              </p>
            ))}
          </div>
          <div className="coord-footer">
            <span>LOCAL / SINGLE USER</span>
            <span>FTS5 · BM25</span>
          </div>
        </div>
      </section>

      {data.counts.papers === 0 && (
        <section className="onboarding-panel">
          <div className="onboarding-copy">
            <span className="eyebrow"><span className="eyebrow-line" />FIRST 10 MINUTES</span>
            <h2>把第一条研究线索接进来。</h2>
            <p>系统现在没有文献，也没有假数据。导入一篇论文，Lattice 会自动抽全文、建索引、生成阅读笔记骨架。</p>
            <Link className="btn btn-primary" to="/papers">
              <Plus size={15} /> 导入第一篇论文
            </Link>
          </div>
          <div className="onboarding-steps">
            <Link to="/papers">
              <span className="step-number">01</span>
              <BookOpen size={17} />
              <div><strong>导入</strong><p>arXiv、DOI、PDF 或 BibTeX</p></div>
              <ArrowUpRight size={14} />
            </Link>
            <Link to="/ideas">
              <span className="step-number">02</span>
              <Lightbulb size={17} />
              <div><strong>假设</strong><p>把直觉写成可证伪的句子</p></div>
              <ArrowUpRight size={14} />
            </Link>
            <Link to="/experiments">
              <span className="step-number">03</span>
              <FlaskConical size={17} />
              <div><strong>实验</strong><p>接入 lab SDK，记录 run 与指标</p></div>
              <ArrowUpRight size={14} />
            </Link>
            <Link to="/drafts">
              <span className="step-number">04</span>
              <PenLine size={17} />
              <div><strong>写作</strong><p>引用、图表、pandoc 导出 PDF</p></div>
              <ArrowUpRight size={14} />
            </Link>
          </div>
        </section>
      )}

      <section className="stat-strip">
        <StatCard icon={<BookOpen size={17} />} label="文献" value={data.counts.papers} note={`${data.counts.unread} 篇未读 · ${data.counts.reading} 篇精读`} />
        <StatCard icon={<Lightbulb size={17} />} label="思路" value={data.counts.ideas} note={`${data.counts.hypotheses} 个假设待验证`} />
        <StatCard icon={<FlaskConical size={17} />} label="实验" value={data.counts.experiments} note={`${data.counts.running_experiments} 个运行中 · ${data.counts.runs} 次 run`} />
        <StatCard icon={<PenLine size={17} />} label="写作" value={totalWords} note={`${data.drafts.length} 份草稿 · ${data.counts.citations} 条可引用文献`} />
      </section>

      <div className="dashboard-grid">
        <section className="panel span-2">
          <PanelHeader
            kicker="READING QUEUE"
            title="继续阅读"
            action={<Link to="/papers" className="text-link">全部文献 <ArrowUpRight size={13} /></Link>}
          />
          <div className="paper-list">
            {data.recent_papers.map((paper, index) => (
              <Link to={`/papers/${paper.id}`} className="paper-row" key={paper.id}>
                <div className="paper-index">{String(index + 1).padStart(2, "0")}</div>
                <div className="paper-row-main">
                  <div className="paper-row-title">{paper.title}</div>
                  <div className="paper-row-meta">
                    <span>{paper.authors.slice(0, 2).join(", ")}</span>
                    <span>{paper.year ?? "—"}</span>
                    <span>{paper.venue || "—"}</span>
                  </div>
                </div>
                <div className="paper-row-tags">
                  {paper.tags.slice(0, 2).map((tag) => (
                    <span className="tag" key={tag}>{tag}</span>
                  ))}
                </div>
                <StatusPill status={paper.status} />
                <ArrowUpRight size={14} className="row-arrow" />
              </Link>
            ))}
            {!data.recent_papers.length && (
              <div className="inline-empty">还没有文献。去文献库导入第一篇 arXiv 论文。</div>
            )}
          </div>
        </section>

        <section className="panel pulse-panel">
          <PanelHeader kicker="WEEKLY PULSE" title="这一周" action={<span className="small muted">更新次数</span>} />
          <div className="pulse-body">
            <div className="pulse-big">
              {data.activity.reduce((sum, day) => sum + day.count, 0)}
              <span>次实体更新</span>
            </div>
            <ActivityBars values={data.activity} />
          </div>
          <div className="pulse-stats">
            <div><strong>{data.counts.annotations}</strong><span>批注</span></div>
            <div><strong>{ideaTotal}</strong><span>思路</span></div>
            <div><strong>{data.tags.length}</strong><span>活跃标签</span></div>
          </div>
        </section>

        <section className="panel inbox-panel">
          <PanelHeader kicker="INBOX" title="待整理" action={<Inbox size={16} className="muted" />} />
          <div className="inbox-list">
            {data.inbox.map((item) => (
              <div className="inbox-item" key={item.id}>
                <button
                  className="inbox-check"
                  onClick={() => process.mutate(item.id)}
                  title="标记已整理"
                  disabled={process.isPending}
                >
                  <Check size={12} />
                </button>
                <p>{item.content}</p>
                <span className="inbox-time">{relativeTime(item.created_at)}</span>
              </div>
            ))}
            {!data.inbox.length && <div className="inline-empty compact">Inbox 清空了。很好。</div>}
          </div>
          <div className="inbox-compose">
            <Plus size={15} />
            <input
              value={inboxDraft}
              onChange={(event) => setInboxDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && inboxDraft.trim()) capture.mutate(inboxDraft.trim());
              }}
              placeholder="记一条不成熟的想法，回车保存…"
            />
            {capture.isPending && <Spinner size={13} />}
          </div>
        </section>

        <section className="panel span-2 feed-panel">
          <PanelHeader
            kicker="DISCIPLINE RADAR"
            title="发现 · 今日候选"
            action={<Link to="/feed" className="text-link">浏览全部 <ArrowUpRight size={13} /></Link>}
          />
          <div className="feed-preview-grid">
            {data.feed.slice(0, 4).map((item) => (
              <Link to="/feed" className="feed-preview" key={item.id}>
                <div className="feed-score">
                  <span>{item.score.toFixed(1)}</span>
                  <small>SCORE</small>
                </div>
                <div>
                  <h4>{truncate(item.title, 88)}</h4>
                  <p>{truncate(item.abstract, 130)}</p>
                  <div className="feed-preview-meta">
                    <span>{item.published}</span>
                    <span>arXiv:{item.arxiv_id}</span>
                  </div>
                </div>
              </Link>
            ))}
            {!data.feed.length && (
              <div className="inline-empty">
                还没有候选论文。到「发现」页抓取最新 arXiv。
              </div>
            )}
          </div>
        </section>

        <section className="panel runs-panel">
          <PanelHeader kicker="LAB LOG" title="实验运行" action={<Link to="/experiments" className="text-link">实验台 <ArrowUpRight size={13} /></Link>} />
          <div className="run-list">
            {data.runs.slice(0, 4).map((run) => (
              <Link
                to={`/experiments/${run.experiment_id}`}
                className="run-row"
                key={run.id}
              >
                <span className={`run-dot run-${run.status}`} />
                <div>
                  <strong>{run.id}</strong>
                  <span>{run.experiment_title}</span>
                </div>
                <span className="run-status">{statusLabel(run.status)}</span>
              </Link>
            ))}
            {!data.runs.length && <div className="inline-empty compact">还没有 run。</div>}
          </div>
        </section>

        <section className="panel questions-panel">
          <PanelHeader kicker="OPEN QUESTIONS" title="当前研究问题" />
          <div className="question-list">
            {data.focus.questions.map((question, index) => (
              <div className="question-item" key={question}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <p>{question}</p>
              </div>
            ))}
          </div>
          <Link to="/ideas" className="questions-footer">
            把问题变成可证伪的假设 <ArrowRight size={14} />
          </Link>
        </section>

        <section className="panel span-2">
          <PanelHeader kicker="WRITING DESK" title="最近草稿" action={<Link to="/drafts" className="text-link">写作台 <ArrowUpRight size={13} /></Link>} />
          <div className="draft-preview-list">
            {data.drafts.map((draft) => (
              <Link to={`/drafts/${draft.id}`} className="draft-preview" key={draft.id}>
                <div className="draft-id">{draft.id}</div>
                <div className="draft-main">
                  <h4>{draft.title}</h4>
                  <p>{truncate(draft.excerpt, 150)}</p>
                </div>
                <div className="draft-meta">
                  <span>{draft.word_count.toLocaleString()} 字</span>
                  <span>{draft.citation_count} 引用</span>
                  <StatusPill status={draft.status} subtle />
                </div>
              </Link>
            ))}
            {!data.drafts.length && <div className="inline-empty">还没有草稿。</div>}
          </div>
        </section>

        <section className="panel idea-summary">
          <PanelHeader kicker="IDEA FUNNEL" title="思路漏斗" />
          <div className="funnel">
            {[
              ["seed", "种子"],
              ["exploring", "探索"],
              ["hypothesis", "假设"],
              ["validated", "验证"],
            ].map(([key, label]) => {
              const count = data.idea_counts[key] ?? 0;
              const max = Math.max(...Object.values(data.idea_counts), 1);
              return (
                <div className="funnel-row" key={key}>
                  <span>{label}</span>
                  <div className="funnel-track">
                    <div style={{ width: `${Math.max((count / max) * 100, 4)}%` }} />
                  </div>
                  <strong>{count}</strong>
                </div>
              );
            })}
          </div>
          <div className="seed-note">
            <Sparkles size={14} />
            <p>索引状态：{data.tools.pdf_export ? "PDF 导出可用" : "PDF 导出等待 tectonic"}</p>
          </div>
        </section>

        <section className="quote-panel">
          <Quote size={22} />
          <p>“A good research system should make the next experiment obvious.”</p>
          <span>— working note</span>
        </section>
      </div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  note,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  note: string;
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span className="stat-icon">{icon}</span>
        <span>{label}</span>
      </div>
      <strong>{value.toLocaleString()}</strong>
      <p>{note}</p>
    </div>
  );
}

function PanelHeader({
  kicker,
  title,
  action,
}: {
  kicker: string;
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="panel-header">
      <div>
        <span className="panel-kicker">{kicker}</span>
        <h3>{title}</h3>
      </div>
      {action}
    </header>
  );
}
