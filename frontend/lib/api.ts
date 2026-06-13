// 镜衡 · API 调用封装
// MVP P0 核心 API

import type {
  StockSearchResult,
  Dossier,
  StrategyVersion,
  Transaction,
} from "@/types";
import { buildUserLlmHeaders } from "@/lib/llmConfig";

// 导出类型供其他模块使用
export type { StockSearchResult, Dossier, StrategyVersion, Transaction } from "@/types";

const API_BASE = "";

// ═══════════════════════════════════════════════
// 股票搜索
// ═══════════════════════════════════════════════

export async function searchStocks(query: string): Promise<StockSearchResult[]> {
  const res = await fetch(`${API_BASE}/api/stock/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error("搜索失败");
  return res.json();
}

// ═══════════════════════════════════════════════
// 卷宗系统
// ═══════════════════════════════════════════════

/** 获取用户所有卷宗 */
export async function getDossierList(): Promise<Dossier[]> {
  const res = await fetch(`${API_BASE}/api/dossier/list`);
  if (!res.ok) throw new Error("获取卷宗列表失败");
  return res.json();
}

/** 删除卷宗（不可恢复） */
export async function deleteDossier(dossierId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/dossier/${dossierId}`, { method: "DELETE" });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody?.detail || "删除卷宗失败");
  }
}

/** 获取卷宗完整详情（含策略版本、交易记录、持仓推算） */
export async function getDossierDetail(dossierId: number): Promise<DossierDetailResponse> {
  const res = await fetch(`${API_BASE}/api/dossier/${dossierId}/detail`);
  if (!res.ok) throw new Error("获取卷宗详情失败");
  return res.json();
}

/** 按股票代码获取卷宗（不存在时返回 404） */
export async function getDossierByStock(stockCode: string): Promise<Dossier> {
  const res = await fetch(`${API_BASE}/api/dossier/by-stock/${encodeURIComponent(stockCode)}`);
  if (!res.ok) throw new Error("卷宗不存在");
  return res.json();
}

/** 保存研究笔记到股票卷宗；卷宗不存在时后端会自动创建 */
export async function updateResearchNote(
  stockCode: string,
  tickerName: string,
  researchNote: string
): Promise<Dossier> {
  const res = await fetch(`${API_BASE}/api/dossier/research-note`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      stock_code: stockCode,
      ticker_name: tickerName,
      research_note: researchNote,
    }),
  });
  if (!res.ok) throw new Error("保存研究笔记失败");
  return res.json();
}

export interface DossierDetailResponse {
  dossier: Dossier;
  strategies: StrategyVersion[];
  transactions: Transaction[];
  position_summary: PositionSummary | null;
}

export interface PositionSummary {
  current_shares: number;
  total_buy_shares: number;
  total_sell_shares: number;
  avg_buy_price: number;
  avg_sell_price: number;
  total_buy_amount: number;
  total_sell_amount: number;
  realized_profit: number;
  cost_basis: number;    // 均买价（每股，含买入佣金）
  total_cost?: number;   // 持仓总成本
  total_commission?: number;
  buy_commission?: number;
  sell_commission?: number;
  commission_min?: number;
  commission_rate?: number;
  commission_rate_label?: string;
  current_price?: number;
  market_value?: number;
  unrealized_profit?: number;
  unrealized_profit_pct?: number;
  holding_return_pct?: number;
  price_source?: string;
  price_updated_at?: string;
  price_unavailable?: boolean;
}

// ═══════════════════════════════════════════════
// 策略版本
// ═══════════════════════════════════════════════

/** 更新策略版本内容 */
export async function updateStrategyVersion(versionId: number, strategyContent: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/strategy/${versionId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ strategy_content: strategyContent }),
  });
  if (!res.ok) throw new Error("更新策略失败");
}

// ═══════════════════════════════════════════════
// 交易记录
// ═══════════════════════════════════════════════

/** 创建交易记录（买入或卖出，不可编辑） */
export async function createTransaction(
  dossierId: number,
  direction: "buy" | "sell",
  price: number,
  quantity: number,
  txnTime: string,
  notes?: string,
  commission?: { commission_min: number; commission_rate_wan: number }
): Promise<Transaction> {
  const res = await fetch(`${API_BASE}/api/transaction/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dossier_id: dossierId,
      direction,
      price,
      quantity,
      txn_time: txnTime,
      notes: notes || "",
      ...(commission
        ? {
            commission_min: commission.commission_min,
            commission_rate_wan: commission.commission_rate_wan,
          }
        : {}),
    }),
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody?.detail || "创建交易记录失败");
  }
  return res.json();
}

// ═══════════════════════════════════════════════
// 数据导出
// ═══════════════════════════════════════════════

/** 导出卷宗数据 */
export async function exportDossier(dossierId: number, format: "json" | "csv"): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/export/dossier/${dossierId}?format=${format}`);
  if (!res.ok) throw new Error("导出失败");
  return res.json();
}

// ═══════════════════════════════════════════════
// 收益曲线
// ═══════════════════════════════════════════════

/** 收益曲线数据点 */
export interface ReturnCurvePoint {
  date: string;
  total_cost: number;
  total_value: number;
  realized_profit: number;
  unrealized_profit: number;
  total_return: number;
  holdings: number;
  total_commission?: number;
}

/** 收益曲线响应 */
export interface ReturnCurveResponse {
  curve: ReturnCurvePoint[];
  summary: {
    total_transactions: number;
    final_holdings: number;
    total_realized_profit: number;
    total_unrealized_profit: number;
    total_return_pct: number;
    total_commission?: number;
    buy_commission?: number;
    sell_commission?: number;
    commission_min?: number;
    commission_rate?: number;
    commission_rate_label?: string;
    current_price?: number;
    market_value?: number;
    unrealized_profit_pct?: number;
    holding_return_pct?: number;
    price_updated_at?: string;
  };
}

/** 单笔佣金 = max(最低佣金, 成交金额 × 费率) */
export function calcTradeCommission(
  amount: number,
  commissionMin: number,
  commissionRate: number
): number {
  if (commissionMin <= 0 && commissionRate <= 0) return 0;
  return Math.round(Math.max(commissionMin, amount * commissionRate) * 100) / 100;
}

export function formatCommissionRateWan(rate: number): string {
  const wan = rate * 10000;
  return Number.isInteger(wan) ? `万${wan}` : `万${wan}`;
}

export function isCommissionConfigured(dossier: {
  commission_min?: number | null;
  commission_rate?: number | null;
}): boolean {
  return dossier.commission_min != null && dossier.commission_rate != null;
}

/** 获取卷宗实时持仓 */
export async function getDossierPosition(dossierId: number): Promise<{
  dossier_id: number;
  stock_code: string;
  stock_name: string;
  position_summary: PositionSummary;
}> {
  const res = await fetch(`${API_BASE}/api/dossier/${dossierId}/position`);
  if (!res.ok) throw new Error("获取实时持仓失败");
  return res.json();
}

/** 投资组合全局概览 */
export async function getPortfolioSummary(): Promise<import("@/types").PortfolioSummary> {
  const res = await fetch(`${API_BASE}/api/portfolio/summary`);
  if (!res.ok) throw new Error("获取投资组合概览失败");
  return res.json();
}

/** 获取收益曲线 */
export async function getReturnCurve(dossierId: number): Promise<ReturnCurveResponse> {
  const res = await fetch(`${API_BASE}/api/dossier/${dossierId}/return-curve`);
  if (!res.ok) throw new Error("获取收益曲线失败");
  return res.json();
}

// ═══════════════════════════════════════════════
// 策略教练
// ═══════════════════════════════════════════════

export interface CoachStreamEvent {
  type: "token" | "done" | "error";
  delta?: string;
  reply?: string;
  state?: string;
  can_confirm?: boolean;
  suggested_questions?: string[];
  can_save_strategy?: boolean;
  strategy_saved?: boolean;
  dossier_id?: number;
  version_id?: number;
  message?: string;
}

/** SSE 流式策略教练对话 */
export async function streamCoachChat(
  body: Record<string, unknown>,
  onEvent: (event: CoachStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch("/api/debate/coach/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...buildUserLlmHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error("无法获取流读取器");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data: ")) continue;
      try {
        onEvent(JSON.parse(line.slice(6)) as CoachStreamEvent);
      } catch {
        // 跳过无法解析的行
      }
    }
  }
}

// ═══════════════════════════════════════════════
// 金融科普
// ═══════════════════════════════════════════════

export interface KnowledgeMessage {
  role: "user" | "agent";
  content: string;
}

export interface KnowledgeRequest {
  selected_text: string;
  context?: string;
  ticker?: string;
  ticker_name?: string;
  question?: string;
  history?: KnowledgeMessage[];
}

export interface KnowledgeResponse {
  explanation: string;
  examples?: string[];
  related_terms?: string[];
}

/** 金融科普 Agent 对话 */
export async function askKnowledge(request: KnowledgeRequest): Promise<KnowledgeResponse> {
  const res = await fetch(`${API_BASE}/api/debate/knowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...buildUserLlmHeaders() },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = typeof err.detail === "string" ? err.detail : "金融科普请求失败";
    throw new Error(detail);
  }
  return res.json();
}

// ═══════════════════════════════════════════════
// 投研工作台
// ═══════════════════════════════════════════════

export type {
  MarketPulse,
  DecisionQuality,
  WorkspaceOverview,
  WorkspaceQueueItem,
  StaleAlertItem,
  BlindSpotInsight,
  PortfolioSummary,
  StrategyAlertItem,
} from "@/types";

/** 今日 A 股市场脉冲 */
export async function getMarketPulse(): Promise<import("@/types").MarketPulse> {
  const res = await fetch(`${API_BASE}/api/market/pulse`);
  if (!res.ok) throw new Error("获取市场脉冲失败");
  return res.json();
}

/** 决策质量得分 */
export async function getDecisionQuality(): Promise<import("@/types").DecisionQuality> {
  const res = await fetch(`${API_BASE}/api/stats/decision-quality`);
  if (!res.ok) throw new Error("获取决策质量失败");
  return res.json();
}

/** 工作台聚合数据（研究队列 + 过期预警 + 盲点雷达） */
export async function getWorkspaceOverview(): Promise<import("@/types").WorkspaceOverview> {
  const res = await fetch(`${API_BASE}/api/workspace/overview`);
  if (!res.ok) throw new Error("获取工作台数据失败");
  return res.json();
}

/** 观点过期预警 */
export async function getStaleAlerts(): Promise<import("@/types").StaleAlerts> {
  const res = await fetch(`${API_BASE}/api/workspace/stale-alerts`);
  if (!res.ok) throw new Error("获取观点过期预警失败");
  return res.json();
}
