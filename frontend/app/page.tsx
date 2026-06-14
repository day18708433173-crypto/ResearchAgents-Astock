"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Eye,
  EyeOff,
  ExternalLink,
  Globe,
  KeyRound,
  Search,
  Server,
  Trash2,
  TrendingUp,
} from "lucide-react";
import {
  getMarketPulse,
  getWorkspaceOverview,
  type MarketPulse,
  type WorkspaceOverview,
} from "@/lib/api";
import {
  clearUserLlmConfig,
  isUserLlmConfigComplete,
  LLM_PROVIDER_PRESETS,
  resolveLlmProviderLabel,
  loadUserLlmConfig,
  normalizeUserLlmConfig,
  saveUserLlmConfig,
  type UserLlmConfig,
} from "@/lib/llmConfig";

function formatDate(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("zh-CN");
}

function formatPct(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function pctColor(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "text-[var(--jh-text-muted)]";
  if (value > 0) return "text-[var(--color-success)]";
  if (value < 0) return "text-[var(--color-error)]";
  return "text-[var(--jh-text-secondary)]";
}

function ratingBadge(rating: string) {
  switch (rating) {
    case "买入":
    case "增持":
      return { label: rating, className: "jh-badge-accent" };
    case "减持":
      return { label: rating, className: "jh-badge-warning" };
    case "卖出":
      return { label: rating, className: "jh-badge-negative" };
    default:
      return { label: rating || "—", className: "jh-badge-muted" };
  }
}

const RESEARCH_LINKS = [
  { name: "同花顺", url: "https://www.10jqka.com.cn/" },
  { name: "东方财富", url: "https://www.eastmoney.com/" },
  { name: "雪球", url: "https://xueqiu.com/" },
  { name: "巨潮资讯", url: "http://www.cninfo.com.cn/" },
  { name: "上交所", url: "https://www.sse.com.cn/" },
  { name: "深交所", url: "https://www.szse.cn/" },
  { name: "财联社", url: "https://www.cls.cn/" },
  { name: "华尔街见闻", url: "https://wallstreetcn.com/" },
] as const;

export default function HomePage() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [pulse, setPulse] = useState<MarketPulse | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceOverview | null>(null);
  const [llmConfig, setLlmConfig] = useState<UserLlmConfig>({
    apiKey: "",
    baseUrl: LLM_PROVIDER_PRESETS[0].baseUrl,
    model: LLM_PROVIDER_PRESETS[0].model,
  });
  const [selectedProvider, setSelectedProvider] = useState("DeepSeek");
  const [showApiKey, setShowApiKey] = useState(false);
  const [llmSaved, setLlmSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getMarketPulse().catch(() => null),
      getWorkspaceOverview().catch(() => null),
    ])
      .then(([pulseData, workspaceData]) => {
        if (cancelled) return;
        setPulse(pulseData);
        setWorkspace(workspaceData);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const stored = loadUserLlmConfig();
    if (!stored) return;
    setLlmConfig(stored);
    setSelectedProvider(resolveLlmProviderLabel(stored));
    setLlmSaved(isUserLlmConfigComplete(stored));
  }, []);

  const queue = workspace?.queue ?? [];
  const portfolio = workspace?.portfolio;
  const strategyAlerts = workspace?.strategy_alerts;
  const alertHighlights = (strategyAlerts?.alerts ?? []).filter(
    (a) => a.status === "near" || a.status === "triggered"
  );

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = searchQuery.trim();
    if (!trimmed) return;
    router.push(`/search?q=${encodeURIComponent(trimmed)}`);
  };

  const handleProviderChange = (label: string) => {
    setSelectedProvider(label);
    const preset = LLM_PROVIDER_PRESETS.find((item) => item.label === label);
    if (!preset) return;
    setLlmConfig((prev) => ({
      ...prev,
      baseUrl: preset.baseUrl,
      model: preset.model,
    }));
    setLlmSaved(false);
  };

  const handleSaveLlmConfig = () => {
    const normalized = normalizeUserLlmConfig(llmConfig);
    setLlmConfig(normalized);
    if (!isUserLlmConfigComplete(normalized)) {
      setLlmSaved(false);
      return;
    }
    saveUserLlmConfig(normalized);
    setLlmSaved(true);
  };

  const handleClearLlmConfig = () => {
    clearUserLlmConfig();
    setLlmConfig({
      apiKey: "",
      baseUrl: LLM_PROVIDER_PRESETS[0].baseUrl,
      model: LLM_PROVIDER_PRESETS[0].model,
    });
    setSelectedProvider("DeepSeek");
    setShowApiKey(false);
    setLlmSaved(false);
  };

  const llmReady = isUserLlmConfigComplete(llmConfig);

  return (
    <div className="min-h-[calc(100vh-3.5rem)] bg-[var(--jh-bg)]">
      <div className="px-4 sm:px-6 py-5">
        <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--jh-text-muted)]">
              <Activity className="w-3.5 h-3.5" />
              Institutional Research Workspace
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-[var(--jh-text)]">
              投研工作台
            </h1>
            <p className="mt-1 text-sm text-[var(--jh-text-secondary)]">
              从机会发现、观点建立到策略复盘，一标的一卷宗，全程留痕、随时复盘。
            </p>
          </div>

          <form onSubmit={handleSearch} className="w-full xl:max-w-xl">
            <div className="flex h-11 items-center rounded-md border border-[var(--jh-border)] bg-[var(--jh-surface)]">
              <Search className="ml-3 w-4 h-4 text-[var(--jh-text-muted)]" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="输入股票名称或代码，进入研究台"
                className="min-w-0 flex-1 bg-transparent px-3 text-sm text-[var(--jh-text)] placeholder:text-[var(--jh-text-muted)] outline-none"
              />
              <button type="submit" className="mr-1.5 h-8 rounded-md bg-[var(--jh-accent)] px-3 text-xs font-medium text-[var(--jh-bg)]">
                打开标的
              </button>
            </div>
          </form>
        </div>

        <section className="terminal-panel mb-5 overflow-hidden">
          <div className="grid gap-0 xl:grid-cols-[minmax(220px,280px)_1fr]">
            <div className="border-b border-[var(--jh-border)] px-4 py-4 xl:border-b-0 xl:border-r">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-md border border-[var(--jh-border-strong)] bg-[var(--jh-bg-2)]">
                  <KeyRound className="h-4 w-4 text-[var(--jh-accent)]" />
                </div>
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-[var(--jh-text)]">模型接入</h2>
                  <p className="mt-0.5 text-xs text-[var(--jh-text-muted)]">
                    {llmSaved ? "正在使用个人模型配置" : "填写后请点击保存，辩论与教练才会使用你的 Key"}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2 text-xs">
                <span
                  className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 ${
                    llmSaved
                      ? "border-[rgba(143,212,195,0.32)] bg-[rgba(143,212,195,0.08)] text-[var(--jh-accent)]"
                      : "border-[var(--jh-border)] bg-[var(--jh-bg-2)] text-[var(--jh-text-muted)]"
                  }`}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {llmSaved ? "已启用" : "待配置"}
                </span>
                <span className="font-mono text-[10px] text-[var(--jh-text-muted)] truncate">
                  {llmConfig.model || "model"}
                </span>
              </div>
            </div>

            <div className="p-4">
              <div className="grid gap-3 lg:grid-cols-[150px_1.15fr_0.9fr]">
                <label className="block">
                  <span className="mb-1.5 block text-[11px] uppercase tracking-[0.14em] text-[var(--jh-text-muted)]">Provider</span>
                  <select
                    value={selectedProvider}
                    onChange={(e) => handleProviderChange(e.target.value)}
                    className="h-10 w-full rounded-md border border-[var(--jh-border)] bg-[var(--jh-bg-2)] px-3 text-sm text-[var(--jh-text)] outline-none focus:border-[var(--jh-accent)]"
                  >
                    {LLM_PROVIDER_PRESETS.map((preset) => (
                      <option key={preset.label} value={preset.label}>{preset.label}</option>
                    ))}
                    <option value="自定义">自定义</option>
                  </select>
                </label>

                <label className="block">
                  <span className="mb-1.5 block text-[11px] uppercase tracking-[0.14em] text-[var(--jh-text-muted)]">Base URL</span>
                  <div className="flex h-10 items-center rounded-md border border-[var(--jh-border)] bg-[var(--jh-bg-2)] focus-within:border-[var(--jh-accent)]">
                    <Server className="ml-3 h-4 w-4 shrink-0 text-[var(--jh-text-muted)]" />
                    <input
                      value={llmConfig.baseUrl}
                      onChange={(e) => {
                        setLlmSaved(false);
                        const baseUrl = e.target.value;
                        setLlmConfig((prev) => ({ ...prev, baseUrl }));
                        setSelectedProvider(resolveLlmProviderLabel({ baseUrl }));
                      }}
                      placeholder="https://api.example.com/v1"
                      className="min-w-0 flex-1 bg-transparent px-3 text-sm text-[var(--jh-text)] placeholder:text-[var(--jh-text-muted)] outline-none"
                    />
                  </div>
                </label>

                <label className="block">
                  <span className="mb-1.5 block text-[11px] uppercase tracking-[0.14em] text-[var(--jh-text-muted)]">Model</span>
                  <input
                    value={llmConfig.model}
                    onChange={(e) => {
                      setLlmSaved(false);
                      setLlmConfig((prev) => ({ ...prev, model: e.target.value }));
                    }}
                    placeholder="deepseek-v4-flash"
                    className="h-10 w-full rounded-md border border-[var(--jh-border)] bg-[var(--jh-bg-2)] px-3 text-sm text-[var(--jh-text)] placeholder:text-[var(--jh-text-muted)] outline-none focus:border-[var(--jh-accent)]"
                  />
                </label>
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_auto] lg:items-end">
                <label className="block">
                  <span className="mb-1.5 block text-[11px] uppercase tracking-[0.14em] text-[var(--jh-text-muted)]">API Key</span>
                  <div className="flex h-10 items-center rounded-md border border-[var(--jh-border)] bg-[var(--jh-bg-2)] focus-within:border-[var(--jh-accent)]">
                    <input
                      type={showApiKey ? "text" : "password"}
                      value={llmConfig.apiKey}
                      onChange={(e) => {
                        setLlmSaved(false);
                        setLlmConfig((prev) => ({ ...prev, apiKey: e.target.value }));
                      }}
                      placeholder="sk-..."
                      className="min-w-0 flex-1 bg-transparent px-3 text-sm text-[var(--jh-text)] placeholder:text-[var(--jh-text-muted)] outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey((value) => !value)}
                      className="mr-1.5 inline-flex h-7 w-7 items-center justify-center rounded-md text-[var(--jh-text-muted)] hover:bg-[var(--jh-surface-container)] hover:text-[var(--jh-text)]"
                      aria-label={showApiKey ? "隐藏 API Key" : "显示 API Key"}
                      title={showApiKey ? "隐藏 API Key" : "显示 API Key"}
                    >
                      {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </label>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleSaveLlmConfig}
                    disabled={!llmReady}
                    className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-[var(--jh-accent)] px-4 text-sm font-medium text-[var(--jh-bg)] transition-colors hover:bg-[var(--jh-accent-2)] disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    保存
                  </button>
                  <button
                    type="button"
                    onClick={handleClearLlmConfig}
                    className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-[var(--jh-border)] text-[var(--jh-text-muted)] transition-colors hover:border-[var(--jh-border-strong)] hover:bg-[var(--jh-bg-2)] hover:text-[var(--jh-text)]"
                    aria-label="清除模型配置"
                    title="清除模型配置"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <div className="grid gap-3 md:grid-cols-2">
          <section className="terminal-panel p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[var(--jh-text)]">今日 A 股脉冲</h2>
              <TrendingUp className="w-4 h-4 text-[var(--jh-text-muted)]" />
            </div>
            {loading ? (
              <div className="skeleton h-16 w-full" />
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div>
                  <div className="text-[11px] text-[var(--jh-text-muted)]">上证指数</div>
                  <div className={`mt-1 text-lg font-semibold numeric ${pctColor(pulse?.sh_index.change_pct)}`}>
                    {formatPct(pulse?.sh_index.change_pct)}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--jh-text-muted)]">深证成指</div>
                  <div className={`mt-1 text-lg font-semibold numeric ${pctColor(pulse?.sz_index.change_pct)}`}>
                    {formatPct(pulse?.sz_index.change_pct)}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--jh-text-muted)]">北向净流入</div>
                  <div className={`mt-1 text-lg font-semibold numeric ${pctColor(pulse?.north_flow_yi)}`}>
                    {pulse?.north_flow_yi != null ? `${pulse.north_flow_yi > 0 ? "+" : ""}${pulse.north_flow_yi}亿` : "--"}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--jh-text-muted)]">涨停家数</div>
                  <div className="mt-1 text-lg font-semibold numeric text-[var(--jh-text)]">
                    {pulse?.limit_up_count ?? "--"}
                  </div>
                </div>
              </div>
            )}
            {pulse?.note ? (
              <p className="mt-2 text-[11px] text-[var(--jh-text-muted)]">{pulse.note}</p>
            ) : null}
          </section>

          <section className="terminal-panel p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-[var(--jh-text)]">常用投研网站</h2>
                <p className="text-[11px] text-[var(--jh-text-muted)]">快捷外链</p>
              </div>
              <Globe className="w-4 h-4 text-[var(--jh-text-muted)]" />
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {RESEARCH_LINKS.map((link) => (
                <a
                  key={link.url}
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex items-center justify-between rounded-md border border-[var(--jh-border)] px-2.5 py-2 text-xs text-[var(--jh-text-secondary)] transition-colors hover:border-[var(--jh-border-strong)] hover:text-[var(--jh-text)]"
                >
                  <span className="truncate">{link.name}</span>
                  <ExternalLink className="ml-1 w-3 h-3 shrink-0 text-[var(--jh-text-muted)] opacity-0 transition-opacity group-hover:opacity-100" />
                </a>
              ))}
            </div>
          </section>
        </div>

        {portfolio && portfolio.items.length > 0 && (
          <section className="terminal-panel mt-5 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-[var(--jh-text)]">投资组合概览</h2>
                <p className="text-xs text-[var(--jh-text-muted)]">基于实时市价的持仓汇总</p>
              </div>
              <BarChart3 className="w-4 h-4 text-[var(--jh-text-muted)]" />
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-md border border-[var(--jh-border)] p-3">
                <div className="text-[11px] text-[var(--jh-text-muted)]">累计买入总额</div>
                <div className="mt-1 text-lg font-semibold numeric text-[var(--jh-text)]">
                  ¥{portfolio.total_buy_deployment.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="rounded-md border border-[var(--jh-border)] p-3">
                <div className="text-[11px] text-[var(--jh-text-muted)]">已实现总盈亏</div>
                <div className={`mt-1 text-lg font-semibold numeric ${portfolio.total_realized_profit >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-error)]"}`}>
                  {portfolio.total_realized_profit >= 0 ? "+" : ""}¥{portfolio.total_realized_profit.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="rounded-md border border-[var(--jh-border)] p-3">
                <div className="text-[11px] text-[var(--jh-text-muted)]">持仓总市值</div>
                <div className="mt-1 text-lg font-semibold numeric text-[var(--jh-text)]">
                  ¥{portfolio.total_market_value.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="rounded-md border border-[var(--jh-border)] p-3">
                <div className="text-[11px] text-[var(--jh-text-muted)]">浮动总盈亏</div>
                <div className={`mt-1 text-lg font-semibold numeric ${portfolio.total_unrealized_profit >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-error)]"}`}>
                  {portfolio.total_unrealized_profit >= 0 ? "+" : ""}¥{portfolio.total_unrealized_profit.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>
            {portfolio.items.filter((i) => i.current_shares > 0).length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {portfolio.items
                  .filter((i) => i.current_shares > 0 && i.weight_pct > 0)
                  .map((item) => (
                    <Link
                      key={item.dossier_id}
                      href={`/dossier/${item.dossier_id}`}
                      className="rounded-md border border-[var(--jh-border)] px-2.5 py-1.5 text-xs text-[var(--jh-text-secondary)] hover:border-[var(--jh-border-strong)]"
                    >
                      {item.stock_name} <span className="text-[var(--jh-accent)]">{item.weight_pct}%</span>
                    </Link>
                  ))}
              </div>
            )}
          </section>
        )}

        {(strategyAlerts?.triggered_count ?? 0) > 0 || (strategyAlerts?.near_count ?? 0) > 0 ? (
          <section className="terminal-panel mt-5 overflow-hidden border-l-4 border-l-[var(--jh-warning)]">
            <div className="border-b border-[var(--jh-border)] px-4 py-3">
              <h2 className="text-sm font-semibold text-[var(--jh-text)]">策略条件提醒</h2>
              <p className="text-xs text-[var(--jh-text-muted)]">
                {strategyAlerts?.triggered_count ?? 0} 条已触发 · {strategyAlerts?.near_count ?? 0} 条接近阈值
              </p>
            </div>
            <div className="divide-y divide-[var(--jh-border)]">
              {alertHighlights.slice(0, 5).map((alert) => (
                <Link
                  key={alert.alert_id}
                  href={`/dossier/${alert.dossier_id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-[var(--jh-bg-2)] transition-colors"
                >
                  <div className="min-w-0">
                    <div className="flex items-center flex-wrap gap-1.5">
                      <span className="text-sm font-medium text-[var(--jh-text)]">
                        {alert.stock_name || alert.stock_code}
                      </span>
                      <span className="jh-badge text-[10px] jh-badge-info">
                        {alert.section === "entry" ? "入场条件" : "离场/风控"}
                      </span>
                      <span className={`jh-badge text-[10px] ${alert.status === "triggered" ? "jh-badge-negative" : "jh-badge-warning"}`}>
                        {alert.status === "triggered" ? "已触发" : "接近阈值"}
                      </span>
                    </div>
                    <div className="text-xs text-[var(--jh-text-muted)] truncate">{alert.message || alert.source_text}</div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 shrink-0 text-[var(--jh-text-muted)]" />
                </Link>
              ))}
            </div>
          </section>
        ) : null}

        <section className="terminal-panel mt-5 overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--jh-border)] px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-[var(--jh-text)]">研究队列</h2>
              <p className="text-xs text-[var(--jh-text-muted)]">裁决评级与持仓状态一览</p>
            </div>
            <Link href="/dossier" className="inline-flex items-center gap-1 text-xs text-[var(--jh-accent)] hover:text-[var(--jh-accent-2)]">
              股票卷宗 <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {loading ? (
            <div className="p-4 space-y-3">
              {[1, 2, 3].map((item) => (
                <div key={item} className="skeleton h-11 w-full" />
              ))}
            </div>
          ) : queue.length === 0 ? (
            <div className="p-10 text-center">
              <BarChart3 className="mx-auto mb-3 w-8 h-8 text-[var(--jh-text-muted)]" />
              <div className="text-sm font-medium text-[var(--jh-text)]">还没有进入跟踪的标的</div>
              <p className="mt-1 text-sm text-[var(--jh-text-muted)]">搜索股票后进入研究台，建立第一条观点记录。</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>标的</th>
                    <th>状态</th>
                    <th>评级</th>
                    <th>策略版本</th>
                    <th>当前持仓</th>
                    <th>最后更新</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {queue.map((item) => {
                    const rating = ratingBadge(item.verdict_rating);
                    return (
                      <tr key={item.dossier_id}>
                        <td>
                          <div className="font-medium text-[var(--jh-text)]">{item.stock_name}</div>
                          <div className="font-mono text-[11px] text-[var(--jh-text-muted)]">{item.stock_code}</div>
                        </td>
                        <td>
                          <span className={`jh-badge text-xs ${item.current_strategy_version > 0 ? "jh-badge-accent" : "jh-badge-warning"}`}>
                            {item.current_strategy_version > 0 ? "跟踪中" : "待建策"}
                          </span>
                        </td>
                        <td>
                          <span className={`jh-badge text-xs ${rating.className}`}>
                            {rating.label}
                          </span>
                        </td>
                        <td className="numeric">V{item.current_strategy_version || 0}</td>
                        <td className="numeric">{item.current_hold_shares || 0} 股</td>
                        <td>{formatDate(item.updated_at)}</td>
                        <td className="text-right">
                          <Link href={`/dossier/${item.dossier_id}`} className="text-xs text-[var(--jh-accent)] hover:text-[var(--jh-accent-2)]">
                            打开
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
