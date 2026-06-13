"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  LayoutDashboard,
  ShieldAlert,
} from "lucide-react";
import { getStaleAlerts, type StaleAlertItem } from "@/lib/api";

const SIDEBAR_WIDTH = 248;
const SIDEBAR_STORAGE_KEY = "jingheng_nav_sidebar_open";

const navItems = [
  { href: "/", label: "工作台", icon: LayoutDashboard },
  { href: "/brainstorm", label: "研究台", icon: BarChart3 },
  { href: "/dossier", label: "股票卷宗", icon: FileText },
];

function staleLevelClass(level: StaleAlertItem["level"]) {
  if (level === "critical") return "border-l-[var(--color-error)] bg-[var(--color-error)]/5";
  if (level === "warning") return "border-l-[var(--color-warning)] bg-[var(--color-warning)]/5";
  return "border-l-[var(--color-success)] bg-[var(--color-success)]/5";
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [staleAlerts, setStaleAlerts] = useState<StaleAlertItem[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (stored === "0") setSidebarOpen(false);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, sidebarOpen ? "1" : "0");
  }, [sidebarOpen]);

  useEffect(() => {
    let cancelled = false;
    getStaleAlerts()
      .then((data) => {
        if (!cancelled) {
          const actionable = (data.alerts || []).filter((item) => item.level !== "ok");
          setStaleAlerts(actionable.slice(0, 6));
        }
      })
      .catch(() => {
        if (!cancelled) setStaleAlerts([]);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  const sidebarToggleClass =
    "hidden lg:inline-flex h-10 w-5 items-center justify-center rounded-r-md border border-l-0 border-[var(--jh-border)] bg-[var(--jh-surface)] text-[var(--jh-text-muted)] shadow-sm transition-colors hover:border-[var(--jh-border-strong)] hover:bg-[var(--jh-bg-2)] hover:text-[var(--jh-text)]";

  return (
    <div className="min-h-screen bg-[var(--jh-bg)] text-[var(--jh-text)] lg:flex">
      <div
        className={`relative hidden lg:block shrink-0 overflow-hidden transition-[width] duration-300 ease-in-out ${
          sidebarOpen ? "w-[248px]" : "w-0"
        }`}
      >
        <aside
          className={`flex h-full min-h-screen flex-col border-r border-[var(--jh-border)] bg-[var(--jh-bg-2)] transition-opacity duration-300 ${
            sidebarOpen ? "opacity-100" : "pointer-events-none opacity-0"
          }`}
          style={{ width: SIDEBAR_WIDTH }}
          aria-hidden={!sidebarOpen}
        >
          <div className="h-14 px-4 border-b border-[var(--jh-border)] flex items-center gap-3">
            <Link href="/" className="flex items-center gap-3 group">
              <div className="w-8 h-8 rounded-md border border-[var(--jh-border-strong)] bg-[var(--jh-surface)] flex items-center justify-center">
                <Activity className="w-4 h-4 text-[var(--jh-accent)]" />
              </div>
              <div>
                <div className="text-sm font-semibold tracking-wide text-[var(--jh-text)]">镜衡</div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--jh-text-muted)]">Research OS</div>
              </div>
            </Link>
          </div>

          <nav className="px-3 py-4 space-y-1">
            {navItems.map((item) => {
              const isActive =
                pathname === item.href ||
                (item.href !== "/" && pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive
                      ? "bg-[var(--jh-surface-container)] text-[var(--jh-text)] border border-[var(--jh-border)]"
                      : "text-[var(--jh-text-secondary)] hover:text-[var(--jh-text)] hover:bg-[rgba(255,255,255,0.03)]"
                  }`}
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="px-4 py-3 border-t border-[var(--jh-border)]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] uppercase tracking-[0.16em] text-[var(--jh-text-muted)]">观点过期预警</span>
              <ShieldAlert className="w-3.5 h-3.5 text-[var(--jh-text-muted)]" />
            </div>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {staleAlerts.length === 0 ? (
                <div className="rounded-md border border-dashed border-[var(--jh-border)] p-3 text-xs text-[var(--jh-text-muted)]">
                  暂无过期预警
                </div>
              ) : (
                staleAlerts.map((alert) => (
                  <Link
                    key={alert.dossier_id}
                    href={`/dossier/${alert.dossier_id}`}
                    className={`block rounded-md border border-[var(--jh-border)] border-l-2 px-2.5 py-2 hover:bg-[rgba(255,255,255,0.03)] ${staleLevelClass(alert.level)}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-[var(--jh-text)] truncate">{alert.stock_name}</span>
                      {alert.current_hold_shares > 0 ? (
                        <span className="text-[10px] text-[var(--jh-text-muted)] shrink-0">{alert.current_hold_shares} 股</span>
                      ) : null}
                    </div>
                    <div className="mt-0.5 text-[10px] text-[var(--jh-text-secondary)] line-clamp-2">{alert.message}</div>
                  </Link>
                ))
              )}
            </div>
          </div>

          <div className="mt-auto px-4 py-3 border-t border-[var(--jh-border)] text-[10px] text-[var(--jh-text-muted)]">
            <div className="flex items-center gap-1.5">
              <Clock3 className="w-3 h-3" />
              A股数据 · 本地缓存
            </div>
          </div>
        </aside>

        {sidebarOpen && (
          <button
            type="button"
            className={`${sidebarToggleClass} absolute right-0 top-1/2 z-20 -translate-y-1/2 translate-x-[calc(100%-20px)]`}
            onClick={() => setSidebarOpen(false)}
            aria-label="收起导航栏"
            title="收起导航栏"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        )}
      </div>

      {!sidebarOpen && (
        <button
          type="button"
          className={`${sidebarToggleClass} fixed left-0 top-[calc(50%+4rem)] z-40 -translate-y-1/2`}
          onClick={() => setSidebarOpen(true)}
          aria-label="展开导航栏"
          title="展开导航栏"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      )}

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-50 h-14 border-b border-[var(--jh-border)] bg-[var(--jh-bg)]/95 backdrop-blur-sm">
          <div className="h-full px-4 sm:px-6 flex items-center justify-between gap-4">
            <Link href="/" className="lg:hidden flex items-center gap-2">
              <Activity className="w-4 h-4 text-[var(--jh-accent)]" />
              <span className="text-sm font-semibold">镜衡</span>
            </Link>

            <div className="hidden md:flex flex-1 items-center gap-3 min-w-0">
              <span className="shrink-0 w-px h-5 bg-[var(--jh-border)]" />
              <p className="text-sm text-[var(--jh-text-muted)] leading-snug truncate">
                <span className="text-[var(--jh-accent)] font-medium">ResearchAgents-Astock</span>
                <span className="mx-1.5 text-[var(--jh-border)]">·</span>
                不替你做决策，陪你形成专属于你的投资策略
              </p>
            </div>

            <nav className="lg:hidden flex items-center gap-1">
              {navItems.map((item) => {
                const isActive =
                  pathname === item.href ||
                  (item.href !== "/" && pathname.startsWith(item.href));
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`p-2 rounded-md ${
                      isActive ? "text-[var(--jh-accent)] bg-[var(--jh-accent-dim)]" : "text-[var(--jh-text-muted)]"
                    }`}
                    aria-label={item.label}
                  >
                    <item.icon className="w-4 h-4" />
                  </Link>
                );
              })}
            </nav>

            <div className="hidden sm:flex items-center gap-3 text-xs text-[var(--jh-text-muted)]">
              <span className="inline-flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--jh-accent)]" />
                Research Live
              </span>
            </div>
          </div>
        </header>

        <main>{children}</main>
      </div>
    </div>
  );
}
