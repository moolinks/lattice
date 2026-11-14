import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Download,
  FolderOpen,
  KeyRound,
  Loader2,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Wrench,
} from "lucide-react";
import { get, patch, post } from "@/lib/api";
import type { AppSettings, Health } from "@/lib/types";
import { formatDateTime, relativeTime } from "@/lib/format";
import { toast } from "@/lib/toast";
import { Spinner } from "@/components/Feedback";

interface AdminStats {
  counts: Record<string, number>;
  db_size_bytes: number;
  data_dir: string;
  tools: { pandoc?: string | null; tectonic?: string | null; pdf_export: boolean };
  last_reindex?: string | null;
}

interface BackupsResponse {
  items: { name: string; size: number; mtime: string }[];
}

function bytes(value: number): string {
  if (value > 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  if (value > 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${value} B`;
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { data: settings, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: () => get<AppSettings>("/settings"),
  });
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => get<Health>("/health"),
  });
  const { data: stats } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: () => get<AdminStats>("/admin/stats"),
  });
  const { data: backups } = useQuery({
    queryKey: ["backups"],
    queryFn: () => get<BackupsResponse>("/admin/backups"),
  });

  const [field, setField] = useState("");
  const [focus, setFocus] = useState("");
  const [questions, setQuestions] = useState("");
  const [keywords, setKeywords] = useState("");
  const [categories, setCategories] = useState("");
  const [titleWeight, setTitleWeight] = useState(10);
  const [bodyWeight, setBodyWeight] = useState(1);
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [dailyFeed, setDailyFeed] = useState(true);

  useEffect(() => {
    if (!settings) return;
    setField(settings.research_field);
    setFocus(settings.research_focus);
    setQuestions(settings.research_questions.join("\n"));
    setKeywords(settings.arxiv_keywords.join("\n"));
    setCategories(settings.arxiv_categories.join(", "));
    setTitleWeight(settings.bm25_title_weight);
    setBodyWeight(settings.bm25_body_weight);
    setModel(settings.anthropic_model);
    setDailyFeed(settings.daily_feed_enabled);
  }, [settings]);

  const save = useMutation({
    mutationFn: () =>
      patch<AppSettings>("/settings", {
        research_field: field,
        research_focus: focus,
        research_questions: questions.split("\n").map((line) => line.trim()).filter(Boolean),
        arxiv_keywords: keywords.split("\n").map((line) => line.trim()).filter(Boolean),
        arxiv_categories: categories.split(/[,，]/).map((item) => item.trim()).filter(Boolean),
        bm25_title_weight: Number(titleWeight),
        bm25_body_weight: Number(bodyWeight),
        anthropic_model: model,
        daily_feed_enabled: dailyFeed,
        ...(apiKey.trim() ? { anthropic_api_key: apiKey.trim() } : {}),
      }),
    onSuccess: () => {
      setApiKey("");
      toast("设置已保存");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["health"] });
      queryClient.invalidateQueries({ queryKey: ["admin-stats"] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const reindex = useMutation({
    mutationFn: () => post<{ fts_rows: number; links: number; papers: number }>("/admin/reindex"),
    onSuccess: (report) => {
      toast(`索引已重建：${report.fts_rows} 行，${report.links} 条关系。`);
      queryClient.invalidateQueries({ queryKey: ["health"] });
      queryClient.invalidateQueries({ queryKey: ["admin-stats"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const backup = useMutation({
    mutationFn: () => post<{ path: string; size: number }>("/admin/backup"),
    onSuccess: (result) => {
      toast(`已创建快照：${result.path.split("\\").pop()}`);
      queryClient.invalidateQueries({ queryKey: ["backups"] });
      queryClient.invalidateQueries({ queryKey: ["admin-stats"] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  if (isLoading) {
    return <div className="page"><div className="loading-inline"><Spinner size={18} /> 载入设置…</div></div>;
  }

  return (
    <div className="page settings-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" />SYSTEM / LOCAL</div>
          <h1>设置</h1>
          <p>单用户、本地优先。配置写入 <code>~/research-data/config.json</code>，不进入代码仓库。</p>
        </div>
        <div className="heading-actions">
          <button className="btn btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
            保存设置
          </button>
        </div>
      </div>

      <div className="settings-grid">
        <section className="panel settings-panel span-2">
          <header className="settings-head">
            <span className="settings-icon"><Sparkles size={17} /></span>
            <div><h2>研究方向</h2><p>用于今日页、arXiv 抓取与 AI prompt 的上下文。</p></div>
          </header>
          <div className="form-grid">
            <div>
              <label className="form-label">研究领域</label>
              <input className="text-input" value={field} onChange={(event) => setField(event.target.value)} />
            </div>
            <div>
              <label className="form-label">子方向</label>
              <input className="text-input" value={focus} onChange={(event) => setFocus(event.target.value)} />
            </div>
          </div>
          <label className="form-label">当前研究问题（每行一个）</label>
          <textarea className="text-area" rows={5} value={questions} onChange={(event) => setQuestions(event.target.value)} />
        </section>

        <section className="panel settings-panel">
          <header className="settings-head">
            <span className="settings-icon"><Search size={17} /></span>
            <div><h2>发现关键词</h2><p>arXiv 查询与相关性打分。</p></div>
          </header>
          <label className="form-label">关键词（每行一个）</label>
          <textarea className="text-area code-font" rows={7} value={keywords} onChange={(event) => setKeywords(event.target.value)} />
          <label className="form-label">arXiv 分类</label>
          <input className="text-input" value={categories} onChange={(event) => setCategories(event.target.value)} />
          <label className="checkbox-row">
            <input type="checkbox" checked={dailyFeed} onChange={(event) => setDailyFeed(event.target.checked)} />
            每日 08:10 自动抓取（APScheduler）
          </label>
        </section>

        <section className="panel settings-panel">
          <header className="settings-head">
            <span className="settings-icon"><SlidersHorizontal size={17} /></span>
            <div><h2>BM25 权重</h2><p>标题 / 正文的检索权重。修改后建议重建索引。</p></div>
          </header>
          <div className="weight-controls">
            <label>
              <span>标题权重 <strong>{titleWeight}</strong></span>
              <input type="range" min={1} max={20} step={0.5} value={titleWeight} onChange={(event) => setTitleWeight(Number(event.target.value))} />
            </label>
            <label>
              <span>正文权重 <strong>{bodyWeight}</strong></span>
              <input type="range" min={0.5} max={5} step={0.5} value={bodyWeight} onChange={(event) => setBodyWeight(Number(event.target.value))} />
            </label>
          </div>
          <p className="settings-note">当前排序：标题 × {titleWeight}，正文 × {bodyWeight}。短于 3 字符的查询自动回退 LIKE。</p>
          <button className="btn btn-ghost btn-sm" onClick={() => reindex.mutate()} disabled={reindex.isPending}>
            {reindex.isPending ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
            立即重建索引
          </button>
        </section>

        <section className="panel settings-panel">
          <header className="settings-head">
            <span className="settings-icon"><KeyRound size={17} /></span>
            <div><h2>AI 助手</h2><p>论文问答与结构化摘要使用 Anthropic API。</p></div>
            <span className={`key-status ${settings?.has_anthropic_key ? "ok" : "warn"}`}>
              {settings?.has_anthropic_key ? "已配置" : "未配置"}
            </span>
          </header>
          <label className="form-label">模型</label>
          <input className="text-input" value={model} onChange={(event) => setModel(event.target.value)} />
          <label className="form-label">API Key {settings?.has_anthropic_key && <span className="muted small">（留空保持不变）</span>}</label>
          <input
            className="text-input"
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={settings?.has_anthropic_key ? "sk-ant-••••••••" : "sk-ant-…"}
            autoComplete="off"
          />
          <p className="settings-note">未配置时，问答接口返回 BM25 定位到的原文证据，不会伪造模型输出。</p>
        </section>

        <section className="panel settings-panel span-2 data-panel">
          <header className="settings-head">
            <span className="settings-icon"><Database size={17} /></span>
            <div><h2>数据与维护</h2><p>所有数据在本地。备份 SQLite 快照，Markdown 建议进 git。</p></div>
            <span className={`health-pill ${health?.status === "ok" ? "ok" : "warn"}`}>
              {health?.status === "ok" ? "健康" : "检查"}
            </span>
          </header>
          <div className="data-grid">
            <div className="data-card">
              <span>数据目录</span>
              <code>{stats?.data_dir ?? settings?.data_dir}</code>
              <button className="text-link" onClick={() => navigator.clipboard.writeText(stats?.data_dir ?? "")}>
                <FolderOpen size={13} /> 复制路径
              </button>
            </div>
            <div className="data-card">
              <span>SQLite</span>
              <strong>{bytes(stats?.db_size_bytes ?? 0)}</strong>
              <small>{stats?.counts.paper ?? 0} 篇文献 · {stats?.counts.link ?? 0} 条关系</small>
            </div>
            <div className="data-card">
              <span>FTS5 索引</span>
              <strong>{health?.fts_rows ?? 0} 行</strong>
              <small>{health?.fts5 === "ok" ? "trigram 分词正常" : "索引异常"}</small>
            </div>
            <div className="data-card">
              <span>当前状态</span>
              <strong className="success-text"><CheckCircle2 size={15} /> 单进程</strong>
              <small>{health?.version ? `v${health.version}` : ""} · 127.0.0.1</small>
            </div>
          </div>
          <div className="data-actions">
            <button className="btn btn-ghost" onClick={() => backup.mutate()} disabled={backup.isPending}>
              {backup.isPending ? <Loader2 size={14} className="spin" /> : <Download size={14} />}
              创建 SQLite 快照
            </button>
            <button className="btn btn-ghost" onClick={() => reindex.mutate()} disabled={reindex.isPending}>
              <RefreshCw size={14} /> 重建 FTS + link
            </button>
          </div>
          <div className="backup-list">
            {(backups?.items ?? []).slice(0, 5).map((item) => (
              <div key={item.name}>
                <span>{item.name}</span>
                <span>{bytes(item.size)}</span>
                <span>{relativeTime(item.mtime)}</span>
              </div>
            ))}
            {!backups?.items.length && <p className="small muted">还没有快照。</p>}
          </div>
        </section>

        <section className="panel settings-panel">
          <header className="settings-head">
            <span className="settings-icon"><Wrench size={17} /></span>
            <div><h2>外部工具</h2><p>导出链路：pandoc → LaTeX → tectonic。</p></div>
          </header>
          <div className="tool-status-list">
            <div>
              <span className={`health-dot ${health?.tools.pandoc ? "ok" : "warn"}`} />
              <div><strong>pandoc</strong><code>{health?.tools.pandoc ?? "未安装"}</code></div>
            </div>
            <div>
              <span className={`health-dot ${health?.tools.tectonic ? "ok" : "warn"}`} />
              <div><strong>tectonic</strong><code>{health?.tools.tectonic ?? "未安装"}</code></div>
            </div>
          </div>
          <p className="settings-note">PDF 导出不可用时，HTML 导出仍可用。安装脚本：<code>scripts/install-tools.ps1</code></p>
        </section>

        <section className="panel settings-panel">
          <header className="settings-head">
            <span className="settings-icon"><ShieldCheck size={17} /></span>
            <div><h2>本地边界</h2><p>这个系统不暴露公网，也没有登录。</p></div>
          </header>
          <ul className="boundary-list">
            <li><CheckCircle2 size={14} /> 后端只监听 127.0.0.1</li>
            <li><CheckCircle2 size={14} /> 无用户体系、无权限模型</li>
            <li><CheckCircle2 size={14} /> 无向量库 / Redis / Celery / Docker</li>
            <li><CheckCircle2 size={14} /> Markdown 为长文本唯一源</li>
          </ul>
          <div className="warning-note">
            <AlertTriangle size={14} />
            <p>备份必须演练恢复。没有验证过恢复的备份，不算是备份。</p>
          </div>
        </section>
      </div>

      <footer className="settings-footer">
        LATTICE · local research workbench · v{settings?.version ?? "0.1.0"} · {formatDateTime(settings?.last_reindex) === "—" ? "尚未重建索引" : `上次重建 ${relativeTime(settings?.last_reindex)}`}
      </footer>
    </div>
  );
}
