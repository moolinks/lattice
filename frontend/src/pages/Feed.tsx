import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BookMarked,
  Check,
  Compass,
  EyeOff,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { get, post, qs } from "@/lib/api";
import type { FeedItem } from "@/lib/types";
import { relativeTime, truncate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { PageSkeleton, EmptyState } from "@/components/Feedback";

interface FeedResponse {
  items: FeedItem[];
  counts: Record<string, number>;
  last_fetched?: string | null;
}

const FILTERS = [
  ["new", "待分拣"],
  ["accepted", "已收藏"],
  ["ignored", "已忽略"],
  ["all", "全部"],
];

export function Feed() {
  const [status, setStatus] = useState("new");
  const [selected, setSelected] = useState(0);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["feed", status],
    queryFn: () => get<FeedResponse>(`/feed${qs({ status, limit: 80 })}`),
  });

  const refresh = useMutation({
    mutationFn: () => post<{ fetched: number; added: number; updated: number }>("/feed/refresh?limit=40"),
    onSuccess: (result) => {
      toast(`arXiv 已刷新：新增 ${result.added} 篇，更新 ${result.updated} 篇。`);
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const accept = useMutation({
    mutationFn: (itemId: number) => post<{ paper_id?: string; status: string }>(`/feed/${itemId}/accept`),
    onSuccess: (result) => {
      if (result.paper_id) toast("已在文献库中，正在打开。");
      else toast("已收藏，后台正在下载全文并建立索引。", "info");
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["papers"] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const ignore = useMutation({
    mutationFn: (itemId: number) => post(`/feed/${itemId}/ignore`),
    onSuccess: () => {
      toast("已忽略，这条不会出现在待分拣中。");
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const items = data?.items ?? [];

  useEffect(() => {
    setSelected(0);
  }, [status]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.key === "j") setSelected((value) => Math.min(value + 1, items.length - 1));
      if (event.key === "k") setSelected((value) => Math.max(value - 1, 0));
      if (event.key === "a" && items[selected]) accept.mutate(items[selected].id);
      if (event.key === "x" && items[selected]) ignore.mutate(items[selected].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, selected, accept, ignore]);

  return (
    <div className="page feed-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" />DISCIPLINE RADAR</div>
          <h1>发现</h1>
          <p>从 arXiv 自动抓取生成式推荐、社交推荐与语义 ID 的候选论文，按关键词与新鲜度打分。</p>
        </div>
        <div className="heading-actions">
          <button className="btn btn-ghost" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
            {refresh.isPending ? "抓取中…" : "刷新 arXiv"}
          </button>
        </div>
      </div>

      <div className="feed-toolbar panel">
        <div className="status-tabs">
          {FILTERS.map(([value, label]) => (
            <button key={value} className={status === value ? "active" : ""} onClick={() => setStatus(value)}>
              {label}
              <span>{value === "all" ? Object.values(data?.counts ?? {}).reduce((a, b) => a + b, 0) : data?.counts[value] ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="feed-toolbar-meta">
          <span className="small muted">
            {data?.last_fetched ? `上次抓取 ${relativeTime(data.last_fetched)}` : "尚未抓取"}
          </span>
          <span className="keyboard-hints">
            <kbd>j</kbd><kbd>k</kbd> 移动 <kbd>a</kbd> 收藏 <kbd>x</kbd> 忽略
          </span>
        </div>
      </div>

      {refresh.isPending && (
        <div className="feed-loading-banner">
          <Sparkles size={15} /> 正在请求 arXiv API（遵守 ≥3s 间隔），并把结果落库缓存…
        </div>
      )}

      {isLoading ? (
        <PageSkeleton />
      ) : (
        <div className="feed-list">
          {items.map((item, index) => (
            <article
              key={item.id}
              className={`feed-card panel ${index === selected ? "selected" : ""}`}
              onClick={() => setSelected(index)}
            >
              <div className="feed-card-score">
                <strong>{item.score.toFixed(1)}</strong>
                <span>RELEVANCE</span>
                <div className="score-bar"><div style={{ width: `${Math.min(item.score * 7, 100)}%` }} /></div>
              </div>
              <div className="feed-card-main">
                <div className="feed-card-meta">
                  <span>{item.published || "—"}</span>
                  <span>arXiv:{item.arxiv_id}</span>
                  <span>{item.authors.slice(0, 2).join(", ")}{item.authors.length > 2 ? " et al." : ""}</span>
                </div>
                <h2>{item.title}</h2>
                <p>{truncate(item.abstract, 360)}</p>
                <div className="feed-card-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={(event) => {
                      event.stopPropagation();
                      accept.mutate(item.id);
                    }}
                    disabled={accept.isPending || item.status !== "new"}
                  >
                    <BookMarked size={13} /> 收藏并导入
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={(event) => {
                      event.stopPropagation();
                      ignore.mutate(item.id);
                    }}
                    disabled={ignore.isPending || item.status !== "new"}
                  >
                    <EyeOff size={13} /> 忽略
                  </button>
                  <a
                    className="btn btn-ghost btn-sm"
                    href={item.arxiv_url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(event) => event.stopPropagation()}
                  >
                    arXiv <ArrowUpRight size={12} />
                  </a>
                  {item.status !== "new" && (
                    <span className="feed-status-note">
                      <Check size={12} /> {item.status === "accepted" ? "已收藏" : "已忽略"}
                    </span>
                  )}
                </div>
              </div>
            </article>
          ))}
          {!items.length && (
            <EmptyState
              icon={<Compass size={30} />}
              title={status === "new" ? "今天还没有候选" : "这个分类是空的"}
              description="点击右上角刷新 arXiv；如果网络受限，可以稍后再试。"
              action={
                <button className="btn btn-primary" onClick={() => refresh.mutate()}>
                  <RefreshCw size={14} /> 抓取最新论文
                </button>
              }
            />
          )}
        </div>
      )}
    </div>
  );
}
