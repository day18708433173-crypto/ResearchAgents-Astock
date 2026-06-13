"""镜衡 Backend — 共享 Pydantic 模型"""

from typing import Optional, List

from pydantic import BaseModel, Field


# ── 股票搜索 ──

class StockSearchResponse(BaseModel):
    ts_code: str
    name: str
    code: str
    price: float = 0.0
    industry: str = ""


# ── 卷宗 ──

class DossierCreateRequest(BaseModel):
    stock_code: str = Field(..., description="股票代码，如 600519.SH")


class DossierResponse(BaseModel):
    dossier_id: int
    stock_code: str
    stock_name: str
    industry: str
    user_id: str
    current_hold_shares: int
    current_strategy_version: int
    commission_min: Optional[float] = None
    commission_rate: Optional[float] = None
    research_note: str = ""
    created_at: str
    updated_at: str


class ResearchNoteUpdateRequest(BaseModel):
    stock_code: str
    ticker_name: str = ""
    research_note: str = ""


class StrategyVersionResponse(BaseModel):
    version_id: int
    dossier_id: int
    version_number: int
    is_active: int
    strategy_content: str  # JSON string
    created_at: str


class TransactionResponse(BaseModel):
    txn_id: int
    dossier_id: int
    direction: str  # 'buy' or 'sell'
    price: float
    quantity: int
    txn_time: str
    notes: str
    created_at: str


class DossierDetailResponse(BaseModel):
    """卷宗完整详情，包含策略版本和交易记录"""
    dossier: DossierResponse
    strategies: List[StrategyVersionResponse]
    transactions: List[TransactionResponse]
    # 持仓推算结果
    position_summary: Optional[dict] = None


class TransactionCreateRequest(BaseModel):
    dossier_id: int
    direction: str = Field(..., description="buy 或 sell")
    price: float = Field(..., gt=0, description="交易价格")
    quantity: int = Field(..., gt=0, description="交易数量")
    txn_time: str = Field(..., description="交易时间 ISO格式")
    notes: str = Field(default="", description="备注")
    commission_min: Optional[float] = Field(default=None, ge=0, description="单笔最低佣金（元），首次录入时必填")
    commission_rate_wan: Optional[float] = Field(
        default=None, gt=0, le=30, description="佣金费率万几，如 2.5 表示万2.5，首次录入时必填"
    )


class StrategyUpdateRequest(BaseModel):
    version_id: int
    strategy_content: str = Field(..., description="策略内容 JSON")


class StrategyCreateRequest(BaseModel):
    """创建策略版本请求"""
    dossier_id: Optional[int] = None
    ticker: str
    ticker_name: str = ""
    current_strategy: str = ""
    coach_conclusion: str = ""  # 兼容旧调用方，与 current_strategy 二选一


class StrategyCreateResponse(BaseModel):
    """创建策略版本响应"""
    version_id: int
    dossier_id: int
    created_at: str
    message: str
    quantifiable_triggers_count: int = 0  # 可量化提醒数量


# ── 辩论 ──

class DebateRequest(BaseModel):
    ticker: str = Field(..., description="股票代码，如 600519.SH")
    ticker_name: str = Field(default="", description="股票名称")
    focus_question: str = Field(default="", description="可选聚焦问题，引导辩论方向")


class DebateRoundResponse(BaseModel):
    round: int
    bull_content: str
    bear_content: str


class DebateResponse(BaseModel):
    success: bool
    ticker: str
    ticker_name: str
    coverage: int
    rounds: List[DebateRoundResponse]
    data_card: dict
    rag_context: Optional[dict] = None
    judge_verdict: Optional[dict] = None
    total_llm_calls: int
    estimated_cost: float
    error: Optional[str] = None


class DebateHistoryItem(BaseModel):
    id: int
    ticker: str
    ticker_name: str = ""
    coverage: Optional[int] = 0
    rating: str = ""
    summary: str = ""
    rounds_count: int = 0
    created_at: str = ""


class DebateHistoryDetail(BaseModel):
    id: int
    ticker: str
    ticker_name: str = ""
    coverage: Optional[int] = 0
    rounds: List[dict] = Field(default_factory=list)
    data_card: Optional[dict] = None
    judge_verdict: Optional[dict] = None
    coach_messages: List[dict] = Field(default_factory=list)
    created_at: str = ""


# ── 数据导出 ──

class ExportRequest(BaseModel):
    dossier_id: int
    format: str  # 'csv', 'json'
    include: List[str]  # ['strategies', 'transactions']


# ── 收益曲线 ──

class ReturnCurvePoint(BaseModel):
    date: str
    total_cost: float  # 累计买入金额（不含佣金）
    total_value: float  # 持仓市值（按该笔成交价估算）
    realized_profit: float  # 已实现盈亏（已扣佣金）
    unrealized_profit: float  # 未实现盈亏
    total_return: float  # 总收益率 (%)
    holdings: int  # 持仓股数
    total_commission: float = 0  # 累计佣金


class ReturnCurveResponse(BaseModel):
    curve: List[ReturnCurvePoint]
    summary: dict


# ── 策略教练 ──

class CoachMessage(BaseModel):
    role: str  # "user" or "coach"
    content: str


class CoachChatRequest(BaseModel):
    ticker: str
    ticker_name: str = ""
    debate_id: Optional[int] = None
    debate_result: dict = None  # 辩论结果摘要
    debate_summary: str = ""  # 兼容前端初始化时传入的摘要
    messages: List[CoachMessage] = []  # 对话历史
    state: str = "opening"  # opening/chatting/reviewing/confirming/done
    # 维度相关字段保留兼容，不再使用
    current_dimension_index: int = 0
    filled_dimensions: List[dict] = []


class DimensionCard(BaseModel):
    """单个维度的策略卡片"""
    dimension: str  # 维度名称
    qualitative_judgment: str  # 定性判断
    category: str = "fundamental"  # 维度分类：fundamental（基本面）/ valuation（估值）
    is_quantifiable: bool = False  # 是否可量化（保留兼容）
    suggested_thresholds: List[dict] = []  # AI建议的阈值
    user_modified_thresholds: List[dict] = []  # 用户修改后的阈值


class CoachChatResponse(BaseModel):
    reply: str
    state: str
    # 维度填充相关
    current_dimension_index: int = 0
    filled_dimensions: List[dict] = []
    total_dimensions: int = 0
    # 兼容旧版
    suggested_dimensions: List[str] = []
    can_confirm: bool = False
    # 新增：当前维度卡片（AI建议）
    current_dimension_card: Optional[dict] = None
    suggested_questions: List[str] = Field(default_factory=list)
    can_save_strategy: bool = False
    dossier_id: Optional[int] = None
    version_id: Optional[int] = None
    strategy_saved: bool = False


class CoachTranscriptSaveRequest(BaseModel):
    messages: List[CoachMessage] = Field(default_factory=list)


# ── 金融科普 ──

class KnowledgeMessage(BaseModel):
    """金融科普对话消息"""
    role: str
    content: str


class KnowledgeRequest(BaseModel):
    """金融科普请求"""
    selected_text: str  # 用户划词关注的术语/概念
    context: str = ""  # 辩论观点来源：多头/空头/裁判
    ticker: str = ""
    ticker_name: str = ""
    question: str = ""  # 当前提问；追问时与 selected_text 区分
    history: List[KnowledgeMessage] = Field(default_factory=list)


class KnowledgeResponse(BaseModel):
    """金融科普响应"""
    explanation: str
    examples: List[str] = []
    related_terms: List[str] = []


# ── 工作台 / 市场脉冲 ──

class IndexPulse(BaseModel):
    name: str
    code: str
    change_pct: Optional[float] = None
    price: Optional[float] = None


class MarketPulseResponse(BaseModel):
    sh_index: IndexPulse
    sz_index: IndexPulse
    north_flow_yi: Optional[float] = None
    limit_up_count: Optional[int] = None
    updated_at: str
    available: bool = True
    note: str = ""


class StaleAlertItem(BaseModel):
    dossier_id: int
    stock_code: str
    stock_name: str
    current_hold_shares: int
    days_since_debate: Optional[int] = None
    last_debate_at: Optional[str] = None
    level: str  # critical | warning | ok
    message: str


class StaleAlertsResponse(BaseModel):
    alerts: List[StaleAlertItem]
    critical_count: int = 0
    warning_count: int = 0


class DecisionQualityBucket(BaseModel):
    total: int = 0
    correct: int = 0
    accuracy_pct: Optional[float] = None


class DecisionQualityItem(BaseModel):
    ticker: str
    ticker_name: str = ""
    verdict_rating: str = ""
    trade_direction: str = ""
    trade_time: str = ""
    pnl_pct: Optional[float] = None
    aligned: bool = False
    correct: bool = False


class DecisionQualityResponse(BaseModel):
    all_time: DecisionQualityBucket
    month: DecisionQualityBucket
    recent_items: List[DecisionQualityItem] = Field(default_factory=list)


class BlindSpotInsight(BaseModel):
    kind: str
    message: str
    severity: str = "info"  # info | warning | critical


class BlindSpotRadarResponse(BaseModel):
    insights: List[BlindSpotInsight]
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    overdue_tickers: List[str] = Field(default_factory=list)


class WorkspaceQueueItem(BaseModel):
    dossier_id: int
    stock_code: str
    stock_name: str
    current_strategy_version: int
    current_hold_shares: int
    updated_at: str
    verdict_rating: str = ""
    drift_status: str = "none"  # none | near_stop | triggered | no_stop_defined
    drift_message: str = ""


class WorkspaceOverviewResponse(BaseModel):
    queue: List[WorkspaceQueueItem]
    stale_alerts: StaleAlertsResponse
    blind_spot: BlindSpotRadarResponse
    portfolio: Optional[dict] = None
    strategy_alerts: Optional[dict] = None


class StrategyAlertItem(BaseModel):
    alert_id: int
    dossier_id: int
    version_id: int
    stock_code: str = ""
    stock_name: str = ""
    section: str
    metric: str
    condition_type: str
    threshold: float
    source_text: str = ""
    status: str = "watching"
    message: str = ""
    current_value: Optional[float] = None


class StrategyAlertsResponse(BaseModel):
    alerts: List[StrategyAlertItem] = Field(default_factory=list)
    near_count: int = 0
    triggered_count: int = 0


class PortfolioSummaryResponse(BaseModel):
    total_buy_deployment: float = 0
    total_realized_profit: float = 0
    total_market_value: float = 0
    total_unrealized_profit: float = 0
    total_assets: float = 0
    items: List[dict] = Field(default_factory=list)
    updated_at: str = ""
