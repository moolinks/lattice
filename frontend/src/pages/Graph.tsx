import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Network, RotateCcw } from "lucide-react";
import { get } from "@/lib/api";
import type { GraphData, GraphNode } from "@/lib/types";
import { entityHref } from "@/lib/format";
import { PageSkeleton, EmptyState } from "@/components/Feedback";

const TYPE_COLORS: Record<string, string> = {
  paper: "#c84b31",
  idea: "#b08b3e",
  experiment: "#245b56",
  draft: "#6b5b8e",
};

const TYPE_LABELS: Record<string, string> = {
  paper: "论文",
  idea: "思路",
  experiment: "实验",
  draft: "草稿",
};

interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export function Graph() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["graph"],
    queryFn: () => get<GraphData>("/graph"),
  });
  const [types, setTypes] = useState<string[]>(["paper", "idea", "experiment", "draft"]);
  const [selected, setSelected] = useState<string | null>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const [, setTick] = useState(0);

  const filtered = useMemo(() => {
    const nodeIds = new Set((data?.nodes ?? []).filter((node) => types.includes(node.type)).map((node) => node.id));
    return {
      nodes: (data?.nodes ?? []).filter((node) => nodeIds.has(node.id)),
      edges: (data?.edges ?? []).filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)),
    };
  }, [data, types]);

  useEffect(() => {
    const count = filtered.nodes.length;
    if (!count) {
      nodesRef.current = [];
      return;
    }
    const nodes: SimNode[] = filtered.nodes.map((node, index) => {
      const angle = (index / count) * Math.PI * 2;
      const radius = 140 + (index % 4) * 55;
      return {
        ...node,
        x: 450 + Math.cos(angle) * radius,
        y: 300 + Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
      };
    });
    nodesRef.current = nodes;
    const nodeMap = new Map(nodes.map((node) => [node.id, node]));
    const edges = filtered.edges
      .map((edge) => ({ source: nodeMap.get(edge.source), target: nodeMap.get(edge.target) }))
      .filter((edge) => edge.source && edge.target);

    // Run the layout to convergence synchronously: stable screenshot, no
    // per-frame React updates, and no animation jank on data-heavy graphs.
    for (let frame = 0; frame < 420; frame += 1) {
      for (const node of nodes) {
        node.vx += (450 - node.x) * 0.0009;
        node.vy += (300 - node.y) * 0.0009;
      }
      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < nodes.length; j += 1) {
          const a = nodes[i];
          const b = nodes[j];
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          const distance = Math.sqrt(dx * dx + dy * dy) || 1;
          if (distance < 150) {
            const force = ((150 - distance) / distance) * 0.035;
            dx *= force;
            dy *= force;
            a.vx += dx;
            a.vy += dy;
            b.vx -= dx;
            b.vy -= dy;
          }
        }
      }
      for (const edge of edges) {
        if (!edge.source || !edge.target) continue;
        const dx = edge.target.x - edge.source.x;
        const dy = edge.target.y - edge.source.y;
        const distance = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (distance - 120) * 0.0028;
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        edge.source.vx += fx;
        edge.source.vy += fy;
        edge.target.vx -= fx;
        edge.target.vy -= fy;
      }
      const velocityLimit = Math.max(0.12, 1.4 * Math.pow(0.994, frame));
      for (const node of nodes) {
        node.vx *= 0.88;
        node.vy *= 0.88;
        node.vx = Math.max(-velocityLimit, Math.min(velocityLimit, node.vx));
        node.vy = Math.max(-velocityLimit, Math.min(velocityLimit, node.vy));
        node.x = Math.max(34, Math.min(866, node.x + node.vx));
        node.y = Math.max(28, Math.min(572, node.y + node.vy));
      }
    }
    nodesRef.current = nodes;
    setTick((value) => value + 1);
  }, [filtered]);

  const nodeMap = new Map(nodesRef.current.map((node) => [node.id, node]));
  const selectedNode = data?.nodes.find((node) => node.id === selected);

  function toggleType(type: string) {
    setTypes((current) =>
      current.includes(type) ? (current.length === 1 ? current : current.filter((value) => value !== type)) : [...current, type],
    );
  }

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="page graph-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" />TRACEABILITY GRAPH</div>
          <h1>知识图谱</h1>
          <p>所有实体通过 front matter、正文 [[ID]]、引用 [@bibkey] 与 run 占位符连接。</p>
        </div>
        <div className="heading-actions">
          <button className="btn btn-ghost" onClick={() => setTypes(["paper", "idea", "experiment", "draft"])}>
            <RotateCcw size={14} /> 重置视图
          </button>
        </div>
      </div>

      <div className="graph-layout">
        <section className="panel graph-canvas-panel">
          <div className="graph-toolbar">
            <div className="graph-legend">
              {Object.entries(TYPE_LABELS).map(([type, label]) => (
                <button
                  key={type}
                  className={types.includes(type) ? "active" : ""}
                  onClick={() => toggleType(type)}
                >
                  <span style={{ background: TYPE_COLORS[type] }} />
                  {label}
                  <strong>{data?.counts[type] ?? 0}</strong>
                </button>
              ))}
            </div>
            <span className="graph-hint">拖动筛选 · 点击节点打开</span>
          </div>
          {filtered.nodes.length ? (
            <svg viewBox="0 0 900 600" className="graph-svg">
              <defs>
                <filter id="node-shadow" x="-30%" y="-30%" width="160%" height="160%">
                  <feDropShadow dx="0" dy="2" stdDeviation="2.5" floodOpacity="0.16" />
                </filter>
              </defs>
              {filtered.edges.map((edge, index) => {
                const source = nodeMap.get(edge.source);
                const target = nodeMap.get(edge.target);
                if (!source || !target) return null;
                return (
                  <line
                    key={`${edge.source}-${edge.target}-${index}`}
                    x1={source.x}
                    y1={source.y}
                    x2={target.x}
                    y2={target.y}
                    className={`graph-edge edge-${edge.relation}`}
                  />
                );
              })}
              {nodesRef.current.map((node) => {
                const radius = 7 + Math.min(node.degree * 1.4, 9);
                const active = selected === node.id;
                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x},${node.y})`}
                    className={`graph-node ${active ? "active" : ""}`}
                    onClick={() => {
                      setSelected(node.id);
                      navigate(entityHref(node.type, node.id));
                    }}
                    onMouseEnter={() => setSelected(node.id)}
                  >
                    <circle r={radius + 6} fill={TYPE_COLORS[node.type]} opacity={active ? 0.18 : 0.06} />
                    <circle r={radius} fill={TYPE_COLORS[node.type]} filter="url(#node-shadow)" />
                    <text y={radius + 14} textAnchor="middle">
                      {node.label.length > 18 ? `${node.label.slice(0, 18)}…` : node.label}
                    </text>
                    <title>{node.id} · {node.label}</title>
                  </g>
                );
              })}
            </svg>
          ) : (
            <EmptyState icon={<Network size={28} />} title="没有可显示的节点" description="实体之间的链接会出现在这里。" />
          )}
          {selectedNode && (
            <div className="graph-inspector">
              <span className="graph-inspector-type" style={{ color: TYPE_COLORS[selectedNode.type] }}>
                {TYPE_LABELS[selectedNode.type]}
              </span>
              <strong>{selectedNode.label}</strong>
              <span>{selectedNode.id} · {selectedNode.degree} 个连接</span>
            </div>
          )}
        </section>

        <aside className="graph-side panel">
          <span className="panel-kicker">MOST CONNECTED</span>
          <h3>图谱枢纽</h3>
          <div className="graph-node-list">
            {(data?.nodes ?? [])
              .slice()
              .sort((a, b) => b.degree - a.degree)
              .slice(0, 12)
              .map((node) => (
                <button key={node.id} onClick={() => navigate(entityHref(node.type, node.id))}>
                  <span className="graph-list-dot" style={{ background: TYPE_COLORS[node.type] }} />
                  <span>
                    <strong>{node.label}</strong>
                    <small>{node.id} · {TYPE_LABELS[node.type]}</small>
                  </span>
                  <span className="graph-degree">{node.degree}</span>
                </button>
              ))}
          </div>
          <div className="graph-stats">
            <div><strong>{data?.nodes.length ?? 0}</strong><span>节点</span></div>
            <div><strong>{data?.edges.length ?? 0}</strong><span>边</span></div>
            <div><strong>{Object.keys(data?.counts ?? {}).length}</strong><span>类型</span></div>
          </div>
        </aside>
      </div>
    </div>
  );
}
