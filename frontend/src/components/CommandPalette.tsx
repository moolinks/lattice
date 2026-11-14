import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  CornerDownLeft,
  FileText,
  FlaskConical,
  Lightbulb,
  PenLine,
  Search,
  SquareStack,
} from "lucide-react";
import { get, qs } from "@/lib/api";
import type { SearchResponse } from "@/lib/types";
import { cn } from "@/lib/format";

const typeIcon: Record<string, typeof FileText> = {
  paper: FileText,
  idea: Lightbulb,
  experiment: FlaskConical,
  draft: PenLine,
};

const typeLabel: Record<string, string> = {
  paper: "论文",
  idea: "思路",
  experiment: "实验",
  draft: "草稿",
};

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setDebounced("");
    setSelected(0);
    window.setTimeout(() => inputRef.current?.focus(), 20);
  }, [open]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 160);
    return () => window.clearTimeout(timer);
  }, [query]);

  const { data, isFetching } = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => get<SearchResponse>(`/search${qs({ q: debounced, limit: 30 })}`),
    enabled: open && debounced.length > 0,
    staleTime: 10_000,
  });

  const items = useMemo(() => data?.items ?? [], [data]);
  useEffect(() => setSelected(0), [data]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSelected((value) => Math.min(value + 1, Math.max(items.length - 1, 0)));
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelected((value) => Math.max(value - 1, 0));
      }
      if (event.key === "Enter" && items[selected]) {
        event.preventDefault();
        go(items[selected].href);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  function go(href: string) {
    navigate(href);
    onClose();
  }

  if (!open) return null;

  return (
    <div className="command-backdrop" onMouseDown={onClose}>
      <div className="command-panel" onMouseDown={(event) => event.stopPropagation()}>
        <div className="command-input-row">
          <Search size={19} className="command-search-icon" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索论文、笔记、思路、实验、草稿…"
            aria-label="全局搜索"
          />
          {isFetching && <span className="command-spinner" />}
          <kbd>ESC</kbd>
        </div>
        <div className="command-results">
          {!debounced && (
            <div className="command-empty">
              <div className="command-hint-grid">
                <div>
                  <strong>搜索整个研究工作区</strong>
                  <p>BM25 命中标题与正文，论文全文按页返回。</p>
                </div>
                <div className="command-shortcuts">
                  <span>
                    <kbd>↑</kbd>
                    <kbd>↓</kbd> 选择
                  </span>
                  <span>
                    <kbd>↵</kbd> 打开
                  </span>
                  <span>
                    <kbd>⌘K</kbd> 关闭
                  </span>
                </div>
              </div>
              <div className="command-brand-mark">
                <SquareStack size={42} strokeWidth={1.1} />
                <span>LATTICE INDEX</span>
              </div>
            </div>
          )}
          {debounced && !isFetching && items.length === 0 && (
            <div className="command-empty">
              <p className="muted">没有找到「{debounced}」。</p>
              <p className="small">中文 1–2 字会自动回退到 LIKE 检索；试试更长、更具体的词。</p>
            </div>
          )}
          {items.map((item, index) => {
            const Icon = typeIcon[item.type] ?? FileText;
            return (
              <button
                key={`${item.type}-${item.entity_id}-${index}`}
                className={cn("command-item", index === selected && "selected")}
                onMouseEnter={() => setSelected(index)}
                onClick={() => go(item.href)}
              >
                <span className={`command-type command-type-${item.type}`}>
                  <Icon size={15} />
                </span>
                <span className="command-item-main">
                  <span className="command-item-title">
                    {item.title}
                    <span className="command-item-type">{typeLabel[item.type] ?? item.type}</span>
                    {item.page && <span className="command-item-page">p.{item.page}</span>}
                  </span>
                  <span
                    className="command-item-snippet"
                    dangerouslySetInnerHTML={{ __html: item.snippet }}
                  />
                </span>
                <ArrowUpRight size={14} className="command-arrow" />
              </button>
            );
          })}
        </div>
        <div className="command-footer">
          <span>{data ? `${data.total} 个结果 · ${data.mode === "bm25" ? "BM25 排序" : "LIKE 回退"}` : "本地 FTS5 索引"}</span>
          <span className="command-enter-hint">
            <CornerDownLeft size={12} /> 打开
          </span>
        </div>
      </div>
    </div>
  );
}
