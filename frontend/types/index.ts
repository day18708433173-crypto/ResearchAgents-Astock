// 镜衡 · 全局 TypeScript 类型定义
// MVP P0 核心类型

// ═══════════════════════════════════════════════
// 股票相关
// ═══════════════════════════════════════════════

export interface Stock {
  stock_code: string;       // 如 "600519.SH"
  name: string;             // 如 "贵州茅台"
  industry: string;         // 如 "白酒"
  market: string;           // 如 "SH" | "SZ"
}

export interface StockSearchResult {
  ts_code: string;
  name: string;
  code: string;
  price?: number;
  industry?: string;
}

// ═══════════════════════════════════════════════
// 卷宗系统 (Dossier)
// ═══════════════════════════════════════════════

export interface Dossier {
  dossier_id: number;
  stock_code: string;
  stock_name: string;
  industry: string;
  user_id: string;
  current_hold_shares: number;  // 当前持仓股数
  current_strategy_version: number;  // 当前生效的策略版本号
  commission_min?: number | null;
  commission_rate?: number | null;
  research_note?: string;
  created_at: string;
  updated_at: string;
}

// ═══════════════════════════════════════════════
// 策略版本系统
// ═══════════════════════════════════════════════

export interface StrategyVersion {
  version_id: number;
  dossier_id: number;
  version_number: number;
  is_active: number;  // SQLite 用 0/1 表示
  strategy_content: string;  // JSON string，需前端解析
  created_at: string;
}

export interface StrategyContent {
  /** 当前策略正文（## 当前策略 块） */
  current_strategy?: string;
  /** @deprecated 旧版字段，仅用于兼容历史数据 */
  coach_conclusion?: string;
  dimensions?: StrategyDimension[];
  debate_summary?: string;
  notes?: string;
  user_decision?: string;
  change_reason?: string;
  confidence?: number;
  overall_rating?: string;
  quantifiable_triggers?: QuantifiableTrigger[];
}

export interface QuantifiableTrigger {
  dimension?: string;
  metric?: string;
  condition?: string;
  action?: string;
  enabled?: boolean;
}

export interface StrategyDimension {
  /** 维度名称，如 "品牌护城河" */
  name?: string;
  /** 教练保存时使用 dimension 字段 */
  dimension?: string;
  /** 维度描述/定义 */
  description?: string;
  /** 用户对该维度的评估/观点 */
  user_view?: string;
  /** 教练保存的定性判断 */
  qualitative_judgment?: string;
  /** fundamental | valuation */
  category?: string;
  is_quantifiable?: boolean;
  suggested_thresholds?: ThresholdItem[];
  user_thresholds?: ThresholdItem[];
  /** 相关指标（可选） */
  metrics?: string[];
  /** 重要性权重 1-5 */
  weight?: number;
}

export interface ThresholdItem {
  metric?: string;
  condition?: string;
  action?: string;
  reason?: string;
}

export interface StrategyChangeReason {
  reason_id: number;
  version_id: number;
  summary: string;          // 修改原因总结
  conversation_ref: string; // 关联的对话片段
  created_at: string;
}

// ═══════════════════════════════════════════════
// 交易记录
// ═══════════════════════════════════════════════

export interface Transaction {
  txn_id: number;
  dossier_id: number;
  direction: "buy" | "sell";
  price: number;
  quantity: number;
  txn_time: string;         // ISO datetime
  notes?: string;
  created_at: string;
}

// ═══════════════════════════════════════════════
// 辩论系统（头脑风暴室）
// ═══════════════════════════════════════════════

export interface DebateMessage {
  role: "bull" | "bear";
  round: number;
  content: string;
}

export interface DebateRound {
  round: number;
  bull_content: string;
  bear_content: string;
}

export interface DebateResponse {
  success: boolean;
  ticker: string;
  ticker_name: string;
  coverage: number;
  rounds: DebateRound[];
  data_card: Record<string, unknown>;
  rag_context?: Record<string, unknown>;
  total_llm_calls: number;
  estimated_cost: number;
  error: string | null;
}

export interface DebateRecord {
  debate_id: number;
  dossier_id: number;
  ticker: string;
  ticker_name: string;
  content: DebateRound[];
  generated_at: string;
  debate_date: string;      // YYYY-MM-DD，用于每日限制
}

// ═══════════════════════════════════════════════
// 收益曲线（P1）
// ═══════════════════════════════════════════════

export interface ProfitPoint {
  date: string;
  cumulative_profit: number;  // 累计盈亏金额
  cumulative_profit_pct: number;  // 累计收益率
}

export interface ProfitCurve {
  dossier_id: number;
  stock_code: string;
  stock_name: string;
  data: ProfitPoint[];
  total_investment: number;   // 总投入金额
  total_return: number;       // 总收益金额
  total_return_pct: number;   // 总收益率
}

// ═══════════════════════════════════════════════
// 投研工作台
// ═══════════════════════════════════════════════

export interface IndexPulse {
  name: string;
  code: string;
  change_pct?: number | null;
  price?: number | null;
}

export interface MarketPulse {
  sh_index: IndexPulse;
  sz_index: IndexPulse;
  north_flow_yi?: number | null;
  limit_up_count?: number | null;
  updated_at: string;
  available: boolean;
  note?: string;
}

export interface StaleAlertItem {
  dossier_id: number;
  stock_code: string;
  stock_name: string;
  current_hold_shares: number;
  days_since_debate?: number | null;
  last_debate_at?: string | null;
  level: "critical" | "warning" | "ok";
  message: string;
}

export interface StaleAlerts {
  alerts: StaleAlertItem[];
  critical_count: number;
  warning_count: number;
}

export interface DecisionQualityBucket {
  total: number;
  correct: number;
  accuracy_pct?: number | null;
}

export interface DecisionQualityItem {
  ticker: string;
  ticker_name: string;
  verdict_rating: string;
  trade_direction: string;
  trade_time: string;
  pnl_pct?: number | null;
  aligned: boolean;
  correct: boolean;
}

export interface DecisionQuality {
  all_time: DecisionQualityBucket;
  month: DecisionQualityBucket;
  recent_items: DecisionQualityItem[];
}

export interface BlindSpotInsight {
  kind: string;
  message: string;
  severity: "info" | "warning" | "critical";
}

export interface BlindSpotRadar {
  insights: BlindSpotInsight[];
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  overdue_tickers: string[];
}

export interface WorkspaceQueueItem {
  dossier_id: number;
  stock_code: string;
  stock_name: string;
  current_strategy_version: number;
  current_hold_shares: number;
  updated_at: string;
  verdict_rating: string;
  drift_status: "none" | "near_stop" | "triggered" | "no_stop_defined";
  drift_message: string;
}

export interface WorkspaceOverview {
  queue: WorkspaceQueueItem[];
  stale_alerts: StaleAlerts;
  blind_spot: BlindSpotRadar;
  portfolio?: PortfolioSummary | null;
  strategy_alerts?: StrategyAlertsSummary | null;
}

export interface PortfolioItem {
  dossier_id: number;
  stock_code: string;
  stock_name: string;
  current_shares: number;
  current_price: number;
  market_value: number;
  realized_profit: number;
  unrealized_profit: number;
  buy_deployment: number;
  weight_pct: number;
}

export interface PortfolioSummary {
  total_buy_deployment: number;
  total_realized_profit: number;
  total_market_value: number;
  total_unrealized_profit: number;
  total_assets: number;
  items: PortfolioItem[];
  updated_at: string;
}

export interface StrategyAlertItem {
  alert_id: number;
  dossier_id: number;
  version_id: number;
  stock_code?: string;
  stock_name?: string;
  section: "entry" | "exit";
  metric: string;
  condition_type: string;
  threshold: number;
  source_text?: string;
  status: "watching" | "near" | "triggered";
  message?: string;
  current_value?: number | null;
}

export interface StrategyAlertsSummary {
  alerts: StrategyAlertItem[];
  near_count: number;
  triggered_count: number;
}
