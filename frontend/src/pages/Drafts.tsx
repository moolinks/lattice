import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  FileText,
  Loader2,
  PenLine,
  Plus,
  Sparkles,
} from "lucide-react";
import { get, post } from "@/lib/api";
import type { Draft, ToolsStatus } from "@/lib/types";
import { relativeTime } from "@/lib/format";
import { toast } from "@/lib/toast";
import { StatusPill } from "@/components/StatusPill";
import { Modal } from "@/components/Modal";
import { EmptyState } from "@/components/Feedback";

interface DraftList {
  items: Draft[];
  tools: ToolsStatus;
}

export function Drafts() {
  const [createOpen, setCreateOpen] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["drafts"],
    queryFn: () => get<DraftList>("/drafts"),
  });

  return (
    <div className="page drafts-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" />WRITING DESK</div>
          <h1>写作</h1>
          <p>Markdown 是唯一源文件。引用从文献库聚合，图表从实验 run 插入，导出交给 pandoc。</p>
        </div>
        <div className="heading-actions">
          <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            <Plus size={15} /> 新草稿
          </button>
        </div>
      </div>

      <div className="writing-statusbar panel">
        <div>
          <span className={`health-dot ${data?.tools.pandoc ? "ok" : "warn"}`} />
          pandoc {data?.tools.pandoc ? "已就绪" : "未安装"}
        </div>
        <div>
          <span className={`health-dot ${data?.tools.tectonic ? "ok" : "warn"}`} />
          tectonic {data?.tools.tectonic ? "已就绪" : "未安装"}
        </div>
        <div className="writing-status-note">
          <Sparkles size={13} /> 引用写法 <code>[@bibkey]</code> · 图表 <code>{"{{run:E0001-R01/curve.png}}"}</code>
        </div>
      </div>

      {isLoading ? (
        <div className="loading-inline"><Loader2 className="spin" size={16} /> 载入草稿…</div>
      ) : (
        <div className="drafts-grid">
          {data?.items.map((draft) => (
            <Link to={`/drafts/${draft.id}`} className="draft-card panel" key={draft.id}>
              <div className="draft-card-top">
                <span className="idea-id">{draft.id}</span>
                <StatusPill status={draft.status} subtle />
              </div>
              <h2>{draft.title}</h2>
              <p className="draft-venue">{draft.venue || "未指定 venue"}</p>
              <p className="draft-excerpt">{draft.excerpt || "空白草稿。"}</p>
              <div className="draft-card-footer">
                <span>{draft.word_count.toLocaleString()} 字</span>
                <span>{draft.citation_count} 引用</span>
                <span>{relativeTime(draft.updated_at)}</span>
                <ArrowUpRight size={14} className="row-arrow" />
              </div>
            </Link>
          ))}
          {!data?.items.length && (
            <EmptyState
              icon={<PenLine size={30} />}
              title="还没有草稿"
              description="从一个可证伪的假设开始，先写 300 字。"
              action={<button className="btn btn-primary" onClick={() => setCreateOpen(true)}><Plus size={14} /> 新建草稿</button>}
            />
          )}
        </div>
      )}

      <CreateDraftModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}

function CreateDraftModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [title, setTitle] = useState("");
  const [venue, setVenue] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const create = useMutation({
    mutationFn: () => post<Draft>("/drafts", { title, venue }),
    onSuccess: (draft) => {
      toast("草稿已创建");
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      onClose();
      navigate(`/drafts/${draft.id}`);
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  return (
    <Modal open={open} onClose={onClose} title="新草稿" subtitle="先写出论证骨架，再补实验与引用。" width="md">
      <div className="form-stack">
        <label className="form-label">标题</label>
        <input className="text-input" value={title} onChange={(event) => setTitle(event.target.value)} autoFocus placeholder="关系条件生成式推荐" />
        <label className="form-label">目标 venue</label>
        <input className="text-input" value={venue} onChange={(event) => setVenue(event.target.value)} placeholder="RecSys 2027 / arXiv preprint" />
      </div>
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={onClose}>取消</button>
        <button className="btn btn-primary" onClick={() => create.mutate()} disabled={!title.trim() || create.isPending}>
          {create.isPending ? <Loader2 size={14} className="spin" /> : <FileText size={14} />}
          创建
        </button>
      </div>
    </Modal>
  );
}
