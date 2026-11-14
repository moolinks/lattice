import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  FlaskConical,
  GripVertical,
  Loader2,
  Plus,
  Save,
  Sparkles,
  X,
} from "lucide-react";
import { get, patch, post } from "@/lib/api";
import type { Idea } from "@/lib/types";
import { relativeTime, statusLabel, truncate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { Modal } from "@/components/Modal";
import { MarkdownEditor } from "@/components/MarkdownEditor";
import { StatusPill } from "@/components/StatusPill";

const COLUMNS = [
  { key: "seed", label: "种子", note: "尚未验证的直觉" },
  { key: "exploring", label: "探索", note: "正在找证据" },
  { key: "hypothesis", label: "假设", note: "可证伪的陈述" },
  { key: "validated", label: "已验证", note: "有实验支持" },
  { key: "parked", label: "搁置", note: "暂缓 / 合并" },
];

export function Ideas() {
  const [params, setParams] = useSearchParams();
  const selectedId = params.get("focus");
  const [createOpen, setCreateOpen] = useState(false);
  const [dragOver, setDragOver] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["ideas"],
    queryFn: () => get<{ items: Idea[]; status_counts: Record<string, number> }>("/ideas"),
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => patch(`/ideas/${id}`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ideas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast("思路状态已更新");
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const open = (id: string) => setParams({ focus: id });
  const close = () => setParams({});

  const grouped = Object.fromEntries(COLUMNS.map((column) => [column.key, [] as Idea[]]));
  for (const idea of data?.items ?? []) {
    (grouped[idea.status] ??= []).push(idea);
  }

  return (
    <div className="page ideas-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" />HYPOTHESIS BOARD</div>
          <h1>思路板</h1>
          <p>把模糊直觉推进成可证伪的假设。拖动卡片改变状态，点击进入工作区。</p>
        </div>
        <div className="heading-actions">
          <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            <Plus size={15} /> 新思路
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="kanban-loading">加载思路…</div>
      ) : (
        <div className="kanban">
          {COLUMNS.map((column) => (
            <section
              key={column.key}
              className={`kanban-column ${dragOver === column.key ? "drag-over" : ""}`}
              onDragOver={(event) => {
                event.preventDefault();
                setDragOver(column.key);
              }}
              onDragLeave={() => setDragOver(null)}
              onDrop={(event) => {
                event.preventDefault();
                setDragOver(null);
                const id = event.dataTransfer.getData("text/idea-id");
                if (id) updateStatus.mutate({ id, status: column.key });
              }}
            >
              <header className={`kanban-head head-${column.key}`}>
                <div>
                  <h3>{column.label}</h3>
                  <span>{column.note}</span>
                </div>
                <strong>{grouped[column.key]?.length ?? 0}</strong>
              </header>
              <div className="kanban-cards">
                {grouped[column.key]?.map((idea) => (
                  <article
                    className="idea-card"
                    key={idea.id}
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.setData("text/idea-id", idea.id);
                      event.dataTransfer.effectAllowed = "move";
                    }}
                    onClick={() => open(idea.id)}
                  >
                    <div className="idea-card-top">
                      <span className="idea-id">{idea.id}</span>
                      <GripVertical size={14} className="drag-grip" />
                    </div>
                    <h4>{idea.title}</h4>
                    <p>{truncate(idea.excerpt, 125)}</p>
                    <div className="idea-card-tags">
                      {idea.tags.slice(0, 3).map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                    </div>
                    <div className="idea-card-footer">
                      <span className={`priority priority-${Math.min(Math.floor(idea.priority / 25), 3)}`}>
                        P{idea.priority}
                      </span>
                      <span>{idea.link_count} 个关联</span>
                      <span>{relativeTime(idea.updated_at)}</span>
                    </div>
                  </article>
                ))}
                {!grouped[column.key]?.length && (
                  <div className="kanban-empty">拖一张卡片到这里</div>
                )}
              </div>
            </section>
          ))}
        </div>
      )}

      <CreateIdeaModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(id) => {
          setCreateOpen(false);
          open(id);
        }}
      />
      {selectedId && <IdeaDrawer id={selectedId} onClose={close} />}
    </div>
  );
}

function CreateIdeaModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [inspiredBy, setInspiredBy] = useState("");
  const [tags, setTags] = useState("");
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!open) {
      setTitle("");
      setSummary("");
      setInspiredBy("");
      setTags("");
    }
  }, [open]);

  const create = useMutation({
    mutationFn: () =>
      post<Idea>("/ideas", {
        title: title.trim(),
        summary: summary.trim(),
        inspired_by: inspiredBy.split(/[,，\s]+/).filter(Boolean),
        tags: tags.split(/[,，\s]+/).filter(Boolean),
        status: "seed",
      }),
    onSuccess: (idea) => {
      toast("思路已创建");
      queryClient.invalidateQueries({ queryKey: ["ideas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onCreated(idea.id);
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="新思路"
      subtitle="先写下最强的版本，再让它接受证伪。"
      width="md"
    >
      <div className="form-stack">
        <label className="form-label">标题</label>
        <input
          className="text-input"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="例如：把社交关系编码为语义 ID 的前缀"
          autoFocus
        />
        <label className="form-label">一句话摘要</label>
        <textarea
          className="text-area"
          rows={3}
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          placeholder="如果……，那么在……条件下，……会提升，因为……"
        />
        <div className="form-grid">
          <div>
            <label className="form-label">灵感来源 ID</label>
            <input
              className="text-input"
              value={inspiredBy}
              onChange={(event) => setInspiredBy(event.target.value)}
              placeholder="P0001, P0003"
            />
          </div>
          <div>
            <label className="form-label">标签</label>
            <input
              className="text-input"
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="semantic-id, social-graph"
            />
          </div>
        </div>
      </div>
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={onClose}>取消</button>
        <button className="btn btn-primary" onClick={() => create.mutate()} disabled={!title.trim() || create.isPending}>
          {create.isPending ? <Loader2 size={14} className="spin" /> : <Plus size={14} />}
          创建
        </button>
      </div>
    </Modal>
  );
}

function IdeaDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("");
  const [dirty, setDirty] = useState(false);

  const { data: idea, isLoading } = useQuery({
    queryKey: ["idea", id],
    queryFn: () => get<Idea>(`/ideas/${id}`),
  });

  useEffect(() => {
    if (idea) {
      setBody(idea.body ?? "");
      setTitle(idea.title);
      setDirty(false);
    }
  }, [idea?.id]);

  const save = useMutation({
    mutationFn: () => patch(`/ideas/${id}`, { body, title }),
    onSuccess: () => {
      setDirty(false);
      toast("思路已保存");
      queryClient.invalidateQueries({ queryKey: ["idea", id] });
      queryClient.invalidateQueries({ queryKey: ["ideas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const updateStatus = useMutation({
    mutationFn: (status: string) => patch(`/ideas/${id}`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["idea", id] });
      queryClient.invalidateQueries({ queryKey: ["ideas"] });
    },
  });

  const promote = useMutation({
    mutationFn: () => post<{ experiment_id: string }>(`/ideas/${id}/promote`),
    onSuccess: (result) => {
      toast(`已创建实验 ${result.experiment_id}`);
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
      onClose();
      navigate(`/experiments/${result.experiment_id}`);
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  return (
    <Modal open onClose={onClose} width="xl" className="idea-drawer">
      {isLoading || !idea ? (
        <div className="drawer-loading"><Loader2 className="spin" size={18} /> 加载思路…</div>
      ) : (
        <div className="idea-drawer-body">
          <div className="idea-drawer-main">
            <div className="drawer-kicker">
              <span>{idea.id}</span>
              <StatusPill status={idea.status} />
              <span className="drawer-updated">{relativeTime(idea.updated_at)}</span>
              <button className="icon-button drawer-close" onClick={onClose}><X size={17} /></button>
            </div>
            <input
              className="idea-title-input"
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
                setDirty(true);
              }}
            />
            <div className="idea-editor-toolbar">
              <div className="small muted">Markdown · [[P0001]] 建立关系 · ⌘S 保存</div>
              <div className="toolbar-buttons">
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => promote.mutate()}
                  disabled={promote.isPending}
                >
                  <FlaskConical size={13} /> 转为实验
                </button>
                <button className="btn btn-primary btn-sm" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
                  {save.isPending ? <Loader2 size={13} className="spin" /> : <Save size={13} />}
                  保存
                </button>
              </div>
            </div>
            <MarkdownEditor
              value={body}
              onChange={(value) => {
                setBody(value);
                setDirty(true);
              }}
              onSave={() => save.mutate()}
              height="calc(100vh - 280px)"
            />
          </div>
          <aside className="idea-drawer-side">
            <section>
              <h4>状态</h4>
              <select
                className="status-select full"
                value={idea.status}
                onChange={(event) => updateStatus.mutate(event.target.value)}
              >
                {COLUMNS.map((column) => (
                  <option key={column.key} value={column.key}>{column.label}</option>
                ))}
              </select>
            </section>
            <section>
              <h4>摘要</h4>
              <p>{idea.summary || "—"}</p>
            </section>
            <section>
              <h4>标签</h4>
              <div className="tag-row">
                {idea.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                {!idea.tags.length && <span className="muted small">无</span>}
              </div>
            </section>
            <section>
              <h4>关联实体</h4>
              <div className="related-list compact">
                {idea.related?.map((item) => (
                  <Link
                    key={`${item.id}-${item.relation}`}
                    to={item.type === "paper" ? `/papers/${item.id}` : item.type === "experiment" ? `/experiments/${item.id}` : item.type === "draft" ? `/drafts/${item.id}` : `/ideas?focus=${item.id}`}
                    onClick={onClose}
                  >
                    <span className="related-type">{item.type}</span>
                    <span>{item.title}</span>
                    <ArrowUpRight size={12} />
                  </Link>
                ))}
                {!idea.related?.length && (
                  <p className="small muted">在正文里写 [[P0001]] 或 [[E0001]] 建立连接。</p>
                )}
              </div>
            </section>
            <section className="idea-side-note">
              <Sparkles size={14} />
              <p><strong>{statusLabel(idea.status)}</strong> · 优先级 {idea.priority}<br />路径：{idea.path?.split("\\").slice(-1)[0]}</p>
            </section>
          </aside>
        </div>
      )}
    </Modal>
  );
}
