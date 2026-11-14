import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import {
  ArrowLeft,
  ArrowUpRight,
  CheckCircle2,
  Clipboard,
  Code2,
  FlaskConical,
  Loader2,
  Play,
  Save,
} from "lucide-react";
import { get, patch, put, qs } from "@/lib/api";
import type { CompareData, Experiment } from "@/lib/types";
import { formatDateTime, relativeTime, statusLabel } from "@/lib/format";
import { toast } from "@/lib/toast";
import { PageSkeleton, EmptyState, Spinner } from "@/components/Feedback";
import { StatusPill } from "@/components/StatusPill";
import { MarkdownEditor } from "@/components/MarkdownEditor";
import { EChart } from "@/components/EChart";

const COLORS = ["#c84b31", "#245b56", "#b08b3e", "#5d6b8a", "#7d5a83"];

export function ExperimentDetail() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [selectedRuns, setSelectedRuns] = useState<string[]>([]);
  const [metricKey, setMetricKey] = useState("");
  const [body, setBody] = useState("");
  const [dirty, setDirty] = useState(false);

  const { data: experiment, isLoading } = useQuery({
    queryKey: ["experiment", id],
    queryFn: () => get<Experiment>(`/experiments/${id}`),
    enabled: Boolean(id),
  });

  useEffect(() => {
    if (!experiment) return;
    setBody(experiment.body ?? "");
    setDirty(false);
    const withMetrics = experiment.runs.filter((run) => run.metric_keys.length).map((run) => run.id);
    setSelectedRuns(withMetrics.slice(0, 4));
    const firstKey =
      experiment.runs.find((run) => run.metric_keys.includes("recall@20"))?.metric_keys.find((key) => key === "recall@20") ??
      experiment.runs[0]?.metric_keys[0] ??
      "";
    setMetricKey(firstKey);
  }, [experiment?.id]);

  const compare = useQuery({
    queryKey: ["compare", id, selectedRuns.join(","), metricKey],
    queryFn: () => get<CompareData>(`/experiments/${id}/compare${qs({ runs: selectedRuns.join(",") })}`),
    enabled: selectedRuns.length > 0,
  });

  const saveNote = useMutation({
    mutationFn: () => put(`/experiments/${id}/note`, { body }),
    onSuccess: () => {
      setDirty(false);
      toast("实验笔记已保存");
      queryClient.invalidateQueries({ queryKey: ["experiment", id] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const update = useMutation({
    mutationFn: (payload: Record<string, unknown>) => patch(`/experiments/${id}`, payload),
    onSuccess: () => {
      toast("实验状态已更新");
      queryClient.invalidateQueries({ queryKey: ["experiment", id] });
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const metricKeys = useMemo(
    () => Array.from(new Set(experiment?.runs.flatMap((run) => run.metric_keys) ?? [])),
    [experiment],
  );

  const chartOption = useMemo<EChartsOption>(() => {
    if (!compare.data || !metricKey) return {};
    const steps = Array.from(
      new Set(
        compare.data.runs.flatMap((run) =>
          (compare.data.series[run.id]?.[metricKey] ?? []).map((point) => point.step),
        ),
      ),
    ).sort((a, b) => a - b);
    return {
      backgroundColor: "transparent",
      color: COLORS,
      grid: { left: 42, right: 20, top: 42, bottom: 34 },
      tooltip: { trigger: "axis", backgroundColor: "#1e211d", borderWidth: 0, textStyle: { color: "#f3efe4", fontSize: 12 } },
      legend: { top: 0, left: 0, itemWidth: 14, itemHeight: 3, textStyle: { color: "#6f6a5e", fontSize: 11 } },
      xAxis: {
        type: "category",
        data: steps,
        boundaryGap: false,
        axisLine: { lineStyle: { color: "#d8d2c3" } },
        axisTick: { show: false },
        axisLabel: { color: "#928b7b", fontSize: 10 },
        name: "step",
        nameTextStyle: { color: "#928b7b", fontSize: 10 },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitLine: { lineStyle: { color: "#e8e2d6", type: "dashed" } },
        axisLabel: { color: "#928b7b", fontSize: 10 },
      },
      series: compare.data.runs.map((run) => {
        const points = compare.data!.series[run.id]?.[metricKey] ?? [];
        const byStep = new Map(points.map((point) => [point.step, point.value]));
        return {
          name: run.id,
          type: "line",
          smooth: 0.25,
          symbolSize: 5,
          showSymbol: false,
          lineStyle: { width: 2 },
          data: steps.map((step) => byStep.get(step) ?? null),
        };
      }),
    };
  }, [compare.data, metricKey]);

  if (isLoading) return <PageSkeleton />;
  if (!experiment) {
    return (
      <div className="page">
        <EmptyState title="没有找到这个实验" action={<Link to="/experiments" className="btn btn-primary">返回实验列表</Link>} />
      </div>
    );
  }

  const latest = experiment.runs[0];

  return (
    <div className="page experiment-detail-page">
      <div className="detail-back-row">
        <Link to="/experiments" className="back-link"><ArrowLeft size={14} /> 实验</Link>
        <span className="crumb-sep">/</span>
        <span>{experiment.id}</span>
      </div>

      <header className="experiment-hero">
        <div>
          <div className="paper-hero-tags">
            <StatusPill status={experiment.status} />
            {experiment.idea_id && (
              <Link className="tag tag-link" to={`/ideas?focus=${experiment.idea_id}`}>
                ← {experiment.idea_id}
              </Link>
            )}
            {typeof latest?.summary?.["demo"] === "boolean" && latest.summary["demo"] && (
              <span className="demo-badge">demo data</span>
            )}
          </div>
          <h1>{experiment.title}</h1>
          <p className="experiment-hypothesis">{experiment.hypothesis}</p>
        </div>
        <div className="paper-hero-actions">
          <select
            className="status-select"
            value={experiment.status}
            onChange={(event) => update.mutate({ status: event.target.value })}
          >
            {["planned", "running", "done", "blocked", "archived"].map((status) => (
              <option key={status} value={status}>{statusLabel(status)}</option>
            ))}
          </select>
          <button
            className="btn btn-ghost"
            onClick={() => {
              navigator.clipboard.writeText(`python -m lab.run --experiment ${experiment.id}`);
              toast("已复制 SDK 命令模板");
            }}
          >
            <Clipboard size={14} /> 运行命令
          </button>
        </div>
      </header>

      <div className="experiment-kpis">
        <div className="kpi"><span>实验 ID</span><strong>{experiment.id}</strong></div>
        <div className="kpi"><span>运行次数</span><strong>{experiment.run_count}</strong></div>
        <div className="kpi"><span>最新 run</span><strong>{latest?.id ?? "—"}</strong></div>
        <div className="kpi">
          <span>最终 Recall@20</span>
          <strong>{latest?.summary?.["final_recall@20"] ? Number(latest.summary["final_recall@20"]).toFixed(4) : "—"}</strong>
        </div>
        <div className="kpi"><span>Git</span><strong className="mono">{latest?.git_commit ?? "—"}</strong></div>
      </div>

      <div className="experiment-layout">
        <section className="panel compare-panel">
          <header className="panel-header">
            <div>
              <span className="panel-kicker">RUN COMPARISON</span>
              <h3>曲线叠加</h3>
            </div>
            <div className="compare-controls">
              <select className="status-select" value={metricKey} onChange={(event) => setMetricKey(event.target.value)}>
                {metricKeys.map((key) => <option key={key} value={key}>{key}</option>)}
              </select>
            </div>
          </header>
          {selectedRuns.length === 0 ? (
            <EmptyState compact title="选择至少一个 run" description="在下方表格勾选要叠加的 run。" />
          ) : compare.isLoading ? (
            <div className="chart-loading"><Spinner /> 载入指标…</div>
          ) : (
            <EChart option={chartOption} height={340} />
          )}
          {compare.data && Object.keys(compare.data.param_diff).length > 0 && (
            <div className="param-diff">
              <h4>关键超参差异</h4>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>参数</th>
                      {compare.data.runs.map((run) => <th key={run.id}>{run.id}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(compare.data.param_diff).map(([key, values]) => (
                      <tr key={key}>
                        <td className="mono">{key}</td>
                        {compare.data!.runs.map((run) => (
                          <td key={run.id}>{String(values[run.id] ?? "—")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>

        <section className="panel run-table-panel">
          <header className="panel-header">
            <div><span className="panel-kicker">RUN LEDGER</span><h3>运行记录</h3></div>
            <span className="small muted">勾选叠加对比</span>
          </header>
          <div className="run-table">
            {experiment.runs.map((run) => (
              <label className={`run-table-row ${selectedRuns.includes(run.id) ? "selected" : ""}`} key={run.id}>
                <input
                  type="checkbox"
                  checked={selectedRuns.includes(run.id)}
                  onChange={(event) =>
                    setSelectedRuns((current) =>
                      event.target.checked ? [...current, run.id] : current.filter((value) => value !== run.id),
                    )
                  }
                />
                <div className="run-table-main">
                  <div>
                    <strong>{run.id}</strong>
                    <span className={`run-dot run-${run.status}`} />
                    <span className="run-table-time">{formatDateTime(run.started_at)}</span>
                  </div>
                  <div className="run-param-chips">
                    {Object.entries(run.params).filter(([key]) => !["demo", "name"].includes(key)).slice(0, 4).map(([key, value]) => (
                      <span key={key}>{key}={String(value)}</span>
                    ))}
                  </div>
                </div>
                <div className="run-table-metric">
                  {run.metric_keys.slice(0, 2).map((key) => {
                    const points = run.metrics?.[key];
                    const last = points?.[points.length - 1]?.value;
                    return (
                      <span key={key}>
                        {key} <strong>{last !== undefined ? last.toFixed(4) : "—"}</strong>
                      </span>
                    );
                  })}
                </div>
                <ArrowUpRight size={13} className="row-arrow" />
              </label>
            ))}
            {!experiment.runs.length && (
              <EmptyState compact icon={<Play size={22} />} title="还没有 run" description="用 lab SDK 或 POST /api/runs 创建。" />
            )}
          </div>
        </section>

        <section className="panel experiment-note-panel">
          <header className="panel-header">
            <div><span className="panel-kicker">LAB NOTEBOOK</span><h3>实验笔记</h3></div>
            <button className="btn btn-primary btn-sm" onClick={() => saveNote.mutate()} disabled={!dirty || saveNote.isPending}>
              {saveNote.isPending ? <Loader2 size={13} className="spin" /> : <Save size={13} />} 保存
            </button>
          </header>
          <MarkdownEditor
            value={body}
            onChange={(value) => {
              setBody(value);
              setDirty(true);
            }}
            onSave={() => saveNote.mutate()}
            height="420px"
          />
        </section>

        <aside className="experiment-side">
          <section className="panel">
            <div className="side-panel-head"><h3>接入 lab SDK</h3><Code2 size={15} /></div>
            <pre className="code-block">{`from lab import Run

with Run(experiment="${experiment.id}", params=cfg) as run:
    for step, metrics in train():
        run.log(step, **metrics)
    run.summary(recall=...)
    run.save_artifact("curve.png")`}</pre>
            <p className="small muted">服务未启动时 SDK 写本地 JSONL，启动后自动补传。</p>
          </section>
          <section className="panel">
            <div className="side-panel-head"><h3>实验结论</h3><CheckCircle2 size={15} /></div>
            <p>{experiment.verdict || "尚未记录 verdict。完成 run 后回到这里写一句可复述的结论。"}</p>
            <div className="experiment-side-meta">
              <span>创建 {relativeTime(experiment.created_at)}</span>
              <span>更新 {relativeTime(experiment.updated_at)}</span>
            </div>
          </section>
          <section className="panel">
            <div className="side-panel-head"><h3>产物</h3><FlaskConical size={15} /></div>
            <div className="artifact-list">
              {latest?.artifacts.map((artifact) => (
                <a
                  key={artifact.id}
                  href={`/api/experiments/${experiment.id}/runs/${latest.id}/artifacts/${artifact.id}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {artifact.name} <ArrowUpRight size={12} />
                </a>
              ))}
              {!latest?.artifacts.length && <span className="small muted">暂无 artifact。</span>}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
