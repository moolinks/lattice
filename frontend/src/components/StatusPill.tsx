import { cn, statusLabel } from "@/lib/format";

export function StatusPill({ status, subtle = false }: { status: string; subtle?: boolean }) {
  return (
    <span className={cn("status-pill", `status-${status}`, subtle && "status-subtle")}>
      <span className="status-dot" />
      {statusLabel(status)}
    </span>
  );
}

export function TypeBadge({ type }: { type: string }) {
  const labels: Record<string, string> = {
    paper: "论文",
    idea: "思路",
    experiment: "实验",
    draft: "草稿",
    run: "运行",
    note: "笔记",
  };
  return <span className={`type-badge type-${type}`}>{labels[type] ?? type}</span>;
}
