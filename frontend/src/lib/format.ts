export function relativeTime(value?: string | null): string {
  if (!value) return "—";
  const then = new Date(value);
  if (Number.isNaN(then.getTime())) return "—";
  const diff = Date.now() - then.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  if (days < 30) return `${Math.floor(days / 7)} 周前`;
  return then.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function compactNumber(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(value);
}

export function truncate(text: string | null | undefined, length = 120): string {
  if (!text) return "";
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > length ? `${clean.slice(0, length - 1)}…` : clean;
}

export function stripMarkdown(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/^---[\s\S]*?---/m, "")
    .replace(/[#>*_`~[\]()]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function authorsLine(authors: string[], max = 3): string {
  if (!authors.length) return "Unknown";
  const shown = authors.slice(0, max).join(", ");
  return authors.length > max ? `${shown} et al.` : shown;
}

export const STATUS_LABEL: Record<string, string> = {
  unread: "未读",
  reading: "精读中",
  read: "已读",
  key: "核心",
  archived: "归档",
  seed: "种子",
  exploring: "探索中",
  hypothesis: "假设",
  validated: "已验证",
  parked: "搁置",
  planned: "计划中",
  running: "进行中",
  done: "已完成",
  blocked: "受阻",
  outline: "大纲",
  writing: "写作中",
  review: "修订中",
  new: "新到",
  accepted: "已收藏",
  ignored: "已忽略",
  failed: "失败",
  complete: "完成",
  queued: "排队",
  all: "全部",
};

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

export function entityHref(type: string, id: string): string {
  if (type === "paper") return `/papers/${id}`;
  if (type === "experiment") return `/experiments/${id}`;
  if (type === "draft") return `/drafts/${id}`;
  if (type === "idea") return `/ideas?focus=${id}`;
  if (type === "run") return `/experiments/${id.split("-R")[0]}`;
  return "/";
}

export function percent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function downloadUrl(url: string, filename?: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename ?? "";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export function cn(...values: (string | false | null | undefined)[]): string {
  return values.filter(Boolean).join(" ");
}

export function dayLabel(date: string): string {
  const d = new Date(`${date}T00:00:00`);
  return ["日", "一", "二", "三", "四", "五", "六"][d.getDay()];
}
