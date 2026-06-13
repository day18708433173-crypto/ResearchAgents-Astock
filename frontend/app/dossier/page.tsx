"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  Calendar,
  Database,
  FileText,
  Plus,
} from "lucide-react";
import { getDossierList, getPortfolioSummary, getWorkspaceOverview, type Dossier } from "@/lib/api";
import type { PortfolioSummary, StrategyAlertsSummary } from "@/types";

function formatDate(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("zh-CN");
}

export default function DossierPage() {
  const router = useRouter();
  const [dossiers, setDossiers] = useState<Dossier[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [strategyAlerts, setStrategyAlerts] = useState<StrategyAlertsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadDossiers();
  }, []);

  const loadDossiers = async () => {
    setLoading(true);
    setError("");
    try {
      const [data, portfolioData, workspaceData] = await Promise.all([
        getDossierList(),
        getPortfolioSummary().catch(() => null),
        getWorkspaceOverview().catch(() => null),
      ]);
      setDossiers(data || []);
      setPortfolio(portfolioData);
      setStrategyAlerts(workspaceData?.strategy_alerts ?? null);
    } catch {
      setDossiers([]);
      setError("加载股票卷宗失败，请检查数据服务后重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-3.5rem)] bg-[var(--jh-bg)]">
      <div className="px-4 sm:px-6 py-6">
        <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--jh-text-muted)]">
              <BookOpen className="w-3.5 h-3.5" />
              Stock Dossier
            </div>
            <h1 className="mt-2 text-2xl font-semibold text-[var(--jh-text)]">股票卷宗</h1>
            <p className="mt-1 text-sm text-[var(--jh-text-secondary)]">
              每只股票一份可追溯档案，记录策略版本、交易动作与复盘证据。
            </p>
          </div>
          <button
            type="button"
            onClick={() => router.push("/brainstorm")}
            className="jh-btn-primary h-9 gap-2 px-4 text-sm"
          >
            <Plus className="w-4 h-4" />
            新建研究
          </button>
        </div>

        {portfolio && portfolio.items.length > 0 && (
          <>
            <div className="mb-3 grid gap-3 md:grid-cols-4">
              {[
                ["累计买入", `¥${portfolio.total_buy_deployment.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`, ""],
                ["已实现盈亏", `${portfolio.total_realized_profit >= 0 ? "+" : ""}¥${portfolio.total_realized_profit.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`, portfolio.total_realized_profit >= 0 ? "text-[var(--jh-accent)]" : "text-[var(--jh-danger)]"],
                ["持仓总市值", `¥${portfolio.total_market_value.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`, ""],
                ["浮动盈亏", `${portfolio.total_unrealized_profit >= 0 ? "+" : ""}¥${portfolio.total_unrealized_profit.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`, portfolio.total_unrealized_profit >= 0 ? "text-[var(--jh-accent)]" : "text-[var(--jh-danger)]"],
              ].map(([label, value, colorClass]) => (
                <div key={String(label)} className="terminal-panel p-4">
                  <div className="text-xs text-[var(--jh-text-muted)]">{label}</div>
                  <div className={`mt-2 text-xl font-semibold numeric ${colorClass || "text-[var(--jh-text)]"}`}>{value}</div>
                </div>
              ))}
            </div>
            {portfolio.items.some((item) => item.weight_pct > 0) && (
              <div className="mb-5 flex flex-wrap items-center gap-2">
                <span className="text-xs text-[var(--jh-text-muted)] mr-1">仓位占比</span>
                {portfolio.items
                  .filter((item) => item.weight_pct > 0)
                  .sort((a, b) => b.weight_pct - a.weight_pct)
                  .map((item) => (
                    <span
                      key={item.dossier_id}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-[var(--jh-border)] bg-[var(--jh-bg-2)] text-xs text-[var(--jh-text-secondary)]"
                    >
                      <span className="font-medium text-[var(--jh-text)]">{item.stock_name}</span>
                      <span className="font-mono text-[10px] text-[var(--jh-text-muted)]">{item.stock_code.split(".")[0]}</span>
                      <span className="text-[var(--jh-accent)] font-semibold">{item.weight_pct}%</span>
                    </span>
                  ))}
              </div>
            )}
          </>
        )}

        {(strategyAlerts?.near_count ?? 0) > 0 || (strategyAlerts?.triggered_count ?? 0) > 0 ? (
          <section className="terminal-panel mb-5 overflow-hidden border-l-4 border-l-[var(--jh-warning)]">
            <div className="border-b border-[var(--jh-border)] px-4 py-3">
              <h2 className="text-sm font-semibold text-[var(--jh-text)]">策略条件接近阈值</h2>
            </div>
            <div className="divide-y divide-[var(--jh-border)]">
              {(strategyAlerts?.alerts ?? [])
                .filter((a) => a.status === "near" || a.status === "triggered")
                .slice(0, 6)
                .map((alert) => (
                  <Link
                    key={alert.alert_id}
                    href={`/dossier/${alert.dossier_id}`}
                    className="flex items-center justify-between px-4 py-3 hover:bg-[var(--jh-bg-2)]"
                  >
                    <div>
                      <div className="flex items-center flex-wrap gap-1.5">
                        <span className="text-sm font-medium text-[var(--jh-text)]">{alert.stock_name}</span>
                        <span className="jh-badge text-[10px] jh-badge-info">
                          {alert.section === "entry" ? "入场条件" : "离场/风控"}
                        </span>
                        <span className={`jh-badge text-[10px] ${alert.status === "triggered" ? "jh-badge-negative" : "jh-badge-warning"}`}>
                          {alert.status === "triggered" ? "已触发" : "接近阈值"}
                        </span>
                      </div>
                      <div className="text-xs text-[var(--jh-text-muted)]">{alert.message}</div>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-[var(--jh-text-muted)]" />
                  </Link>
                ))}
            </div>
          </section>
        ) : null}

        <section className="terminal-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--jh-border)] px-4 py-3">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-[var(--jh-text-muted)]" />
              <h2 className="text-sm font-semibold text-[var(--jh-text)]">研究档案</h2>
            </div>
            <span className="text-xs text-[var(--jh-text-muted)]">按最近更新时间排序</span>
          </div>

          {loading ? (
            <div className="p-4 space-y-2">
              {[1, 2, 3, 4].map((item) => (
                <div key={item} className="skeleton h-11 w-full" />
              ))}
            </div>
          ) : error ? (
            <div className="p-10 text-center">
              <AlertCircle className="mx-auto mb-3 w-8 h-8 text-[var(--jh-danger)]" />
              <p className="text-sm text-[var(--jh-text-secondary)]">{error}</p>
              <button type="button" onClick={loadDossiers} className="jh-btn-secondary mt-4 px-4 py-2 text-sm">
                重试
              </button>
            </div>
          ) : dossiers.length === 0 ? (
            <div className="p-12 text-center">
              <FileText className="mx-auto mb-3 w-8 h-8 text-[var(--jh-text-muted)]" />
              <h3 className="text-sm font-medium text-[var(--jh-text)]">暂无卷宗</h3>
              <p className="mt-1 text-sm text-[var(--jh-text-muted)]">进入研究台完成一次观点记录后，会自动生成卷宗。</p>
              <button type="button" onClick={() => router.push("/brainstorm")} className="jh-btn-primary mt-5 h-9 px-4 text-sm">
                打开研究台
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>标的</th>
                    <th>行业</th>
                    <th>状态</th>
                    <th>策略版本</th>
                    <th>持仓</th>
                    <th>创建日期</th>
                    <th>最后更新</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {dossiers.map((item) => {
                    const isActive = item.current_strategy_version > 0;
                    return (
                      <tr key={item.dossier_id}>
                        <td>
                          <div className="font-medium text-[var(--jh-text)]">{item.stock_name}</div>
                          <div className="font-mono text-[11px] text-[var(--jh-text-muted)]">{item.stock_code}</div>
                        </td>
                        <td>{item.industry || "-"}</td>
                        <td>
                          <span className={`jh-badge text-xs ${isActive ? "jh-badge-accent" : "jh-badge-warning"}`}>
                            {isActive ? "跟踪中" : "策略草稿"}
                          </span>
                        </td>
                        <td className="numeric">V{item.current_strategy_version || 0}</td>
                        <td className="numeric">{item.current_hold_shares || 0} 股</td>
                        <td>
                          <span className="inline-flex items-center gap-1.5">
                            <Calendar className="w-3 h-3 text-[var(--jh-text-muted)]" />
                            {formatDate(item.created_at)}
                          </span>
                        </td>
                        <td>{formatDate(item.updated_at)}</td>
                        <td className="text-right">
                          <Link
                            href={`/dossier/${item.dossier_id}`}
                            className="inline-flex items-center gap-1 text-xs text-[var(--jh-accent)] hover:text-[var(--jh-accent-2)]"
                          >
                            打开 <ArrowRight className="w-3.5 h-3.5" />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
