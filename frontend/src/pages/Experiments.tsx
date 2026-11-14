import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  FlaskConical,
  Loader2,
  Plus,
  Sparkles,
} from "lucide-react";
import { get, post } from "@/lib/api";
import type { Experiment, Idea } from "@/lib/types";
import { relativeTime } from "@/lib/format";
import { toast } from "@/lib/toast";
import { StatusPill } from "@/components/StatusPill";
import { Sparkline } from "@/components/Charts";
import { Modal } from "@/components/Modal";
import { EmptyState } from "@/components/Feedback";

interface ExperimentList {
  items: Experiment[];
  status_counts: Record<string, number>;
}

export function Experiments() {
  const [createOpen, setCreateOpen] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["experiments"],
    queryFn: () => get<ExperimentList>("/experiments"),
  });

  const counts = data?.status_counts ?? {};
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);

  return (
    <div className="page experiments-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" />EXPERIMENT LAB</div>
          <h1>实验</h1>
          <p>从思路到可复现的 run。参数、指标、Git 状态与产物统一收进本地实验账本。</p>
        </div>
        <div className="heading-actions">
          <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            <Plus size={15} /> 新实验
          </button>
        </div>
      </div>

      <div className="experiment-summary">
        {[
          ["planned", "计划中", "等待排期"],
          ["running", "进行中", "正在产生 metrics"],
          ["done", "已完成", "有结论可复盘"],
          ["blocked", "受阻", "缺少数据/算力"],
        ].map(([key, label, note]) => (
          <div className={`summary-cell summary-${key}`} key={key}>
            <span>{label}</span>
            <strong>{counts[key] ?? 0}</strong>
            <small>{note}</small>
          </div>
        ))}
        <div className="summary-cell summary-total">
          <span>总计</span>
          <strong>{total}</strong>
          <small>{data?.items.reduce((sum, exp) => sum + exp.run_count, 0) ?? 0} 次 run</small>
        </div>
      </div>

      {isLoading ? (
        <div className="loading-inline"><Loader2 className="spin" size={16} /> 载入实验…</div>
      ) : (
        <div className="experiment-list">
          {data?.items.map((experiment) => {
            const latest = experiment.latest_run;
            return (
              <Link to={`/experiments/${experiment.id}`} className="experiment-card panel" key={experiment.id}>
                <div className="experiment-card-left">
                  <div className="experiment-id-row">
                    <span className="idea-id">{experiment.id}</span>
                    <StatusPill status={experiment.status} />
                    {experiment.idea_id && <span className="tag tag-mono">← {experiment.idea_id}</span>}
                  </div>
                  <h2>{experiment.title}</h2>
                  <p>{experiment.hypothesis || experiment.excerpt}</p>
                  <div className="experiment-meta-row">
                    <span>{experiment.run_count} runs</span>
                    <span>更新于 {relativeTime(experiment.updated_at)}</span>
                    {latest && <span>最新 {latest.id}</span>}
                    {typeof latest?.summary?.["demo"] === "boolean" && latest.summary["demo"] && (
                      <span className="demo-badge">demo data</span>
                    )}
                  </div>
                </div>
                <div className="experiment-card-right">
                  <div className="experiment-spark">
                    {latest?.metric_keys.length ? (
                      <>
                        <Sparkline values={[0.45, 0.5, 0.54, 0.58, 0.6, 0.63, 0.65]} />
                        <span>指标曲线见详情</span>
                      </>
                    ) : (
                      <span className="muted small">暂无 metrics</span>
                    )}
                  </div>
                  <ArrowUpRight size={16} className="row-arrow" />
                </div>
              </Link>
            );
          })}
          {!data?.items.length && (
            <EmptyState
              icon={<FlaskConical size={30} />}
              title="还没有实验"
              description="从思路板把假设推进为实验，或在 lab SDK 中创建 run。"
              action={<button className="btn btn-primary" onClick={() => setCreateOpen(true)}><Plus size={14} /> 新实验</button>}
            />
          )}
        </div>
      )}

      <CreateExperimentModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}

function CreateExperimentModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [title, setTitle] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [ideaId, setIdeaId] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: ideas } = useQuery({
    queryKey: ["ideas"],
    queryFn: () => get<{ items: Idea[] }>("/ideas"),
    enabled: open,
  });

  const create = useMutation({
    mutationFn: () => post<Experiment>("/experiments", { title, hypothesis, idea_id: ideaId || null }),
    onSuccess: (experiment) => {
      toast("实验已创建");
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
      onClose();
      navigate(`/experiments/${experiment.id}`);
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  return (
    <Modal open={open} onClose={onClose} title="新实验" subtitle="一个实验只验证一个可证伪的假设。" width="md">
      <div className="form-stack">
        <label className="form-label">标题</label>
        <input className="text-input" value={title} onChange={(event) => setTitle(event.target.value)} autoFocus placeholder="关系前缀对冷启动 Recall@20 的影响" />
        <label className="form-label">假设</label>
        <textarea className="text-area" rows={3} value={hypothesis} onChange={(event) => setHypothesis(event.target.value)} placeholder="在……条件下，……相对基线提升，因为……" />
        <label className="form-label">关联思路</label>
        <select className="status-select full" value={ideaId} onChange={(event) => setIdeaId(event.target.value)}>
          <option value="">不关联</option>
          {ideas?.items.map((idea) => <option value={idea.id} key={idea.id}>{idea.id} · {idea.title}</option>)}
        </select>
      </div>
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={onClose}>取消</button>
        <button className="btn btn-primary" onClick={() => create.mutate()} disabled={!title.trim() || create.isPending}>
          {create.isPending ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />}
          创建实验
        </button>
      </div>
    </Modal>
  );
}
