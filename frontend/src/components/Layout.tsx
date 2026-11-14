import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  Command,
  Compass,
  FlaskConical,
  LayoutDashboard,
  Lightbulb,
  Menu,
  Network,
  PenLine,
  Plus,
  Search,
  Settings,
  X,
} from "lucide-react";
import { get } from "@/lib/api";
import type { Health } from "@/lib/types";
import { cn } from "@/lib/format";
import { CommandPalette } from "./CommandPalette";
import { QuickCapture } from "./QuickCapture";

const NAV_GROUPS = [
  {
    label: "研究",
    items: [
      { to: "/", label: "今日", icon: LayoutDashboard, end: true },
      { to: "/papers", label: "文献库", icon: BookOpen },
      { to: "/feed", label: "发现", icon: Compass },
      { to: "/ideas", label: "思路板", icon: Lightbulb },
    ],
  },
  {
    label: "产出",
    items: [
      { to: "/experiments", label: "实验", icon: FlaskConical },
      { to: "/drafts", label: "写作", icon: PenLine },
      { to: "/graph", label: "图谱", icon: Network },
    ],
  },
];

function pageTitle(pathname: string): string {
  if (pathname === "/") return "今日";
  if (pathname.startsWith("/papers/")) return "论文详情";
  if (pathname === "/papers") return "文献库";
  if (pathname === "/feed") return "发现";
  if (pathname === "/ideas") return "思路板";
  if (pathname.startsWith("/experiments/")) return "实验详情";
  if (pathname === "/experiments") return "实验";
  if (pathname.startsWith("/drafts/")) return "写作台";
  if (pathname === "/drafts") return "写作";
  if (pathname === "/graph") return "知识图谱";
  if (pathname === "/settings") return "设置";
  return "Lattice";
}

export function Layout() {
  const location = useLocation();
  const [searchOpen, setSearchOpen] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => get<Health>("/health"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen((value) => !value);
      }
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "i") {
        event.preventDefault();
        setCaptureOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <aside className={cn("sidebar", mobileOpen && "sidebar-open")}>
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <img src="/icon.svg" alt="" />
          </div>
          <div>
            <div className="brand-name">LATTICE</div>
            <div className="brand-sub">RESEARCH WORKBENCH</div>
          </div>
          <button className="icon-button sidebar-close" onClick={() => setMobileOpen(false)}>
            <X size={18} />
          </button>
        </div>

        <div className="focus-card">
          <span className="focus-eyebrow">CURRENT FIELD</span>
          <strong>生成式推荐</strong>
          <span className="focus-arrow">↳</span>
          <span className="focus-sub">社交关系推荐</span>
          <div className="focus-lines">
            <span />
            <span />
            <span />
          </div>
        </div>

        <nav className="main-nav">
          {NAV_GROUPS.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => cn("nav-item", isActive && "active")}
                >
                  <item.icon size={17} strokeWidth={1.8} />
                  <span>{item.label}</span>
                  <span className="nav-notice" />
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <NavLink to="/settings" className={({ isActive }) => cn("nav-item", isActive && "active")}>
            <Settings size={17} strokeWidth={1.8} />
            <span>设置</span>
          </NavLink>
          <div className="local-status">
            <span className={`health-dot ${health?.status === "ok" ? "ok" : "warn"}`} />
            <div>
              <strong>{health?.status === "ok" ? "LOCAL ENGINE" : "CHECK ENGINE"}</strong>
              <span>{health ? `FTS5 · ${health.fts_rows} 条索引` : "连接中…"}</span>
            </div>
          </div>
        </div>
      </aside>

      {mobileOpen && <div className="sidebar-scrim" onClick={() => setMobileOpen(false)} />}

      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)}>
              <Menu size={20} />
            </button>
            <span className="topbar-kicker">R / 01</span>
            <h1>{pageTitle(location.pathname)}</h1>
          </div>
          <div className="topbar-actions">
            <button className="search-trigger" onClick={() => setSearchOpen(true)}>
              <Search size={15} />
              <span>搜索整个工作区</span>
              <kbd>
                <Command size={10} />K
              </kbd>
            </button>
            <button className="btn btn-ghost capture-trigger" onClick={() => setCaptureOpen(true)}>
              <Plus size={15} />
              记录
            </button>
            <div className="topbar-avatar" title="本地单用户">研</div>
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>

      <CommandPalette open={searchOpen} onClose={() => setSearchOpen(false)} />
      <QuickCapture open={captureOpen} onClose={() => setCaptureOpen(false)} />
    </div>
  );
}
