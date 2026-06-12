"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  FileText,
  TrendingUp,
  TrendingDown,
  History,
  Plus,
  Calendar,
  DollarSign,
  BarChart3,
  Edit3,
  Layers,
  Target,
  Wallet,
  X,
  Check,
  Download,
  AlertCircle,
  Loader2,
  Info,
  Trash2,
} from "lucide-react";
import {
  getDossierDetail,
  createTransaction,
  updateStrategyVersion,
  getReturnCurve,
  exportDossier,
  deleteDossier,
  calcTradeCommission,
  formatCommissionRateWan,
  isCommissionConfigured,
  type ReturnCurveResponse,
} from "@/lib/api";
import type { DossierDetailResponse } from "@/lib/api";
import type { Transaction } from "@/types";
import { useToast } from "@/components/toast-provider";
import { ReturnCurveChart } from "@/components/ReturnCurveChart";
import { StrategyCardView, parseStrategyContent } from "@/components/StrategyCardView";

type TabType = "overview" | "strategy" | "transactions";

export default function DossierDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { toast } = useToast();
  const dossierId = Number(params.id);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [data, setData] = useState<DossierDetailResponse | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [returnCurve, setReturnCurve] = useState<ReturnCurveResponse | null>(null);
  const [exporting, setExporting] = useState<"json" | "csv" | null>(null);

  const [showTxnDialog, setShowTxnDialog] = useState(false);
  const [txnForm, setTxnForm] = useState({
    direction: "buy" as "buy" | "sell",
    price: "",
    quantity: "",
    txn_time: new Date().toISOString().slice(0, 16),
    notes: "",
    commission_min: "5",
    commission_rate_wan: "2.5",
  });
  const [txnSubmitting, setTxnSubmitting] = useState(false);
  const [txnError, setTxnError] = useState("");

  const [editingVersion, setEditingVersion] = useState<number | null>(null);
  const [editContent, setEditContent] = useState("");

  const [strategySaveError, setStrategySaveError] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadDetail();
  }, [dossierId]);

  useEffect(() => {
    if (!showTxnDialog) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowTxnDialog(false);
        setTxnError("");
      }
    };
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [showTxnDialog]);

  const loadDetail = async () => {
    setLoading(true);
    setLoadError("");
    setNotFound(false);
    try {
      const res = await getDossierDetail(dossierId);
      setData(res);
      try {
        const curve = await getReturnCurve(dossierId);
        setReturnCurve(curve);
      } catch {
        setReturnCurve(null);
      }
    } catch (e: unknown) {
      setData(null);
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("404") || msg.includes("不存在")) {
        setNotFound(true);
      } else {
        setLoadError("加载卷宗详情失败，请检查网络后重试");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (format: "json" | "csv") => {
    setExporting(format);
    try {
      const result = await exportDossier(dossierId, format);
      const blob = new Blob(
        [
          format === "json"
            ? JSON.stringify(result, null, 2)
            : String((result as { content?: string }).content || ""),
        ],
        { type: format === "json" ? "application/json" : "text/csv;charset=utf-8" }
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dossier-${dossierId}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      toast(`已导出 ${format.toUpperCase()} 文件`, "success");
    } catch {
      toast("导出失败，请稍后重试", "error");
    } finally {
      setExporting(null);
    }
  };

  const handleCreateTransaction = async () => {
    if (!txnForm.price || !txnForm.quantity) return;
    const needsCommissionSetup = data && !isCommissionConfigured(data.dossier) && data.transactions.length === 0;
    if (needsCommissionSetup) {
      const min = Number(txnForm.commission_min);
      const wan = Number(txnForm.commission_rate_wan);
      if (!Number.isFinite(min) || min < 0 || !Number.isFinite(wan) || wan <= 0) {
        setTxnError("请填写有效的佣金参数");
        return;
      }
    }
    setTxnError("");
    try {
      setTxnSubmitting(true);
      await createTransaction(
        dossierId,
        txnForm.direction,
        Number(txnForm.price),
        Number(txnForm.quantity),
        txnForm.txn_time,
        txnForm.notes,
        needsCommissionSetup
          ? {
              commission_min: Number(txnForm.commission_min),
              commission_rate_wan: Number(txnForm.commission_rate_wan),
            }
          : undefined
      );
      setShowTxnDialog(false);
      setTxnForm({
        direction: "buy",
        price: "",
        quantity: "",
        txn_time: new Date().toISOString().slice(0, 16),
        notes: "",
        commission_min: txnForm.commission_min,
        commission_rate_wan: txnForm.commission_rate_wan,
      });
      loadDetail();
    } catch (e: any) {
      const msg = e?.message || "创建交易记录失败";
      setTxnError(msg.includes("超过") ? msg : "创建交易记录失败，请重试");
      console.error("创建交易记录失败", e);
    } finally {
      setTxnSubmitting(false);
    }
  };

  const handleDeleteDossier = async () => {
    setDeleting(true);
    try {
      await deleteDossier(dossierId);
      toast("卷宗已删除，可重新进入头脑风暴室记录", "success");
      router.push("/dossier");
    } catch {
      toast("删除卷宗失败，请重试", "error");
    } finally {
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const handleSaveStrategy = async () => {
    if (!editingVersion) return;
    setStrategySaveError("");
    try {
      await updateStrategyVersion(editingVersion, editContent);
      setEditingVersion(null);
      toast("策略已保存", "success");
      loadDetail();
    } catch {
      setStrategySaveError("保存策略失败，请重试");
      toast("保存策略失败", "error");
    }
  };

  const formatMoney = (n: number) => `¥${n.toLocaleString()}`;
  const formatDate = (s: string) => new Date(s).toLocaleDateString("zh-CN");

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--jh-bg)]">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 pt-8 space-y-4">
          <div className="skeleton h-8 w-48" />
          <div className="glass-card p-6 space-y-3">
            <div className="skeleton h-5 w-full" />
            <div className="skeleton h-5 w-3/4" />
            <div className="skeleton h-32 w-full" />
          </div>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="min-h-screen bg-[var(--jh-bg)] flex flex-col items-center justify-center px-6">
        <AlertCircle className="w-10 h-10 text-[var(--jh-danger)] mb-3 opacity-60" />
        <p className="text-[var(--jh-text-secondary)] text-sm mb-4">{loadError}</p>
        <button type="button" onClick={loadDetail} className="jh-btn-primary text-sm px-4 py-2">重试</button>
      </div>
    );
  }

  if (notFound || !data) {
    return (
      <div className="min-h-screen bg-[var(--jh-bg)] flex flex-col items-center justify-center px-6">
        <FileText className="w-10 h-10 text-[var(--jh-text-muted)] mb-3 opacity-40" />
        <p className="text-[var(--jh-text-secondary)] text-sm mb-4">卷宗不存在或已被删除</p>
        <button type="button" onClick={() => router.push("/dossier")} className="jh-btn-primary text-sm px-4 py-2">返回卷宗列表</button>
      </div>
    );
  }

  const { dossier, strategies, transactions, position_summary } = data;
  const needsCommissionSetup = !isCommissionConfigured(dossier) && transactions.length === 0;
  const commissionMin = dossier.commission_min ?? position_summary?.commission_min ?? 0;
  const commissionRate = dossier.commission_rate ?? position_summary?.commission_rate ?? 0;
  const commissionLabel =
    position_summary?.commission_rate_label ||
    (commissionRate > 0 ? formatCommissionRateWan(commissionRate) : "");

  return (
    <div className="min-h-screen bg-[var(--jh-bg)]">
      {/* 顶部导航 */}
      <div className="sticky top-14 z-10 bg-[var(--jh-bg-2)] border-b border-[var(--jh-border)]">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between gap-3">
          <button type="button" onClick={() => router.push("/dossier")} className="flex items-center gap-2 text-[var(--jh-text-secondary)] hover:text-[var(--jh-text)] transition-colors">
            <ArrowLeft className="w-5 h-5" /><span>返回</span>
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleExport("json")}
              disabled={exporting !== null}
              className="flex items-center gap-1.5 text-xs text-[var(--jh-text-muted)] hover:text-[var(--jh-accent)] px-2 py-1.5 rounded-lg hover:bg-[rgba(255,255,255,0.04)] transition-colors"
              aria-label="导出 JSON"
            >
              {exporting === "json" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              JSON
            </button>
            <button
              type="button"
              onClick={() => handleExport("csv")}
              disabled={exporting !== null}
              className="flex items-center gap-1.5 text-xs text-[var(--jh-text-muted)] hover:text-[var(--jh-accent)] px-2 py-1.5 rounded-lg hover:bg-[rgba(255,255,255,0.04)] transition-colors"
              aria-label="导出 CSV"
            >
              {exporting === "csv" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              CSV
            </button>
            <button
              type="button"
              onClick={() => setShowDeleteConfirm(true)}
              className="flex items-center gap-1.5 text-xs text-[var(--jh-danger)] hover:bg-[rgba(255,122,122,0.1)] px-2 py-1.5 rounded-lg transition-colors"
              aria-label="删除卷宗"
            >
              <Trash2 className="w-3.5 h-3.5" />
              删除
            </button>
            <span className="text-xs text-[var(--jh-text-muted)] hidden sm:inline">更新于 {formatDate(dossier.updated_at)}</span>
          </div>
        </div>
      </div>

      {/* 标题区域 */}
      <div className="max-w-4xl mx-auto px-6 pt-6 pb-4">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-12 h-12 rounded-xl bg-[var(--jh-accent-dim)] flex items-center justify-center border border-[var(--jh-border-accent)]">
            <FileText className="w-6 h-6 text-[var(--jh-accent)]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-[var(--jh-text)]">{dossier.stock_name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-sm text-[var(--jh-text-muted)] font-mono">{dossier.stock_code}</span>
              {dossier.industry && <span className="jh-badge jh-badge-info text-xs">{dossier.industry}</span>}
            </div>
          </div>
        </div>

        {/* Tab 切换 */}
        <div className="flex gap-2 border-b border-[var(--jh-border)] overflow-x-auto" role="tablist" aria-label="卷宗详情">
          {[
            { key: "overview", label: "概览", icon: Target },
            { key: "strategy", label: "策略版本", icon: Layers },
            { key: "transactions", label: "交易记录", icon: Wallet },
          ].map((tab) => (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.key}
              onClick={() => setActiveTab(tab.key as TabType)}
              className={`flex items-center gap-2 px-4 py-3 text-sm transition-colors whitespace-nowrap flex-shrink-0 ${
                activeTab === tab.key
                  ? "text-[var(--jh-accent)] border-b-2 border-[var(--jh-accent)]"
                  : "text-[var(--jh-text-secondary)] hover:text-[var(--jh-text)]"
              }`}
            >
              <tab.icon className="w-4 h-4" />{tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* 内容区域 */}
      <div className="max-w-4xl mx-auto px-6 pb-16">
        {/* 概览 Tab */}
        {activeTab === "overview" && (
          <div className="space-y-6 animate-fade-in-up" role="tabpanel">
            {/* 收益计算规则说明 */}
            <div className="glass-card p-4 border border-[var(--jh-border-accent)] bg-[rgba(99,230,208,0.04)]">
              <div className="flex items-start gap-3">
                <Info className="w-4 h-4 text-[var(--jh-accent)] mt-0.5 flex-shrink-0" />
                <div className="text-xs text-[var(--jh-text-secondary)] leading-relaxed space-y-1.5">
                  <p className="font-medium text-[var(--jh-text)]">收益计算规则</p>
                  {isCommissionConfigured(dossier) ? (
                    <p>
                      本卷宗佣金：单笔最低 <strong>{commissionMin}</strong> 元，费率 <strong>{commissionLabel}</strong>
                      （单笔佣金 = max(最低佣金, 成交金额 × 费率)）；买卖双向收取。
                    </p>
                  ) : (
                    <p>首次录入交易时需设置佣金参数，之后本卷宗所有交易按同一规则计费。</p>
                  )}
                  <p>买入成本计入佣金；卖出收入扣除佣金。印花税等其他费用忽略不计。</p>
                  <p>收益率 = (已实现盈亏 + 未实现盈亏) ÷ 累计投入（含买入佣金）；未实现盈亏以最近一笔成交价估算。</p>
                </div>
              </div>
            </div>

            {returnCurve && returnCurve.curve.length > 0 && (
              <div className="glass-card p-6">
                <h2 className="text-base font-semibold text-[var(--jh-text)] mb-4 flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-[var(--jh-accent)]" />
                  收益曲线
                  {returnCurve.summary && (
                    <span className={`text-sm font-normal ml-auto ${returnCurve.summary.total_return_pct >= 0 ? "text-[var(--jh-accent)]" : "text-[var(--jh-danger)]"}`}>
                      {returnCurve.summary.total_return_pct >= 0 ? "+" : ""}{returnCurve.summary.total_return_pct.toFixed(2)}%
                    </span>
                  )}
                </h2>
                <ReturnCurveChart points={returnCurve.curve} />
              </div>
            )}
            {position_summary && (
              <div className="glass-card p-6">
                <h2 className="text-base font-semibold text-[var(--jh-text)] mb-4 flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-[var(--jh-accent)]" />持仓概览
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="p-4 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)]">
                    <div className="text-xs text-[var(--jh-text-muted)] mb-1">当前持仓</div>
                    <div className="text-lg font-bold text-[var(--jh-text)]">{position_summary.current_shares} 股</div>
                  </div>
                  <div className="p-4 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)]">
                    <div className="text-xs text-[var(--jh-text-muted)] mb-1">均买价</div>
                    <div className="text-lg font-bold text-[var(--jh-text)]">{formatMoney(position_summary.cost_basis)}</div>
                    {position_summary.total_cost != null && position_summary.current_shares > 0 && (
                      <div className="text-xs text-[var(--jh-text-muted)] mt-0.5">总成本 {formatMoney(position_summary.total_cost)}</div>
                    )}
                  </div>
                  <div className="p-4 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)]">
                    <div className="text-xs text-[var(--jh-text-muted)] mb-1">累计买入</div>
                    <div className="text-lg font-bold text-[var(--jh-accent)]">{formatMoney(position_summary.total_buy_amount)}</div>
                  </div>
                  <div className="p-4 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)]">
                    <div className="text-xs text-[var(--jh-text-muted)] mb-1">累计卖出</div>
                    <div className="text-lg font-bold text-[var(--jh-danger)]">{formatMoney(position_summary.total_sell_amount)}</div>
                  </div>
                </div>
                <div className="mt-4 p-4 rounded-lg bg-[rgba(99,230,208,0.05)] border border-[var(--jh-border-accent)]">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-[var(--jh-text-secondary)]">已实现盈亏（已扣佣金）</span>
                    <span className={`text-lg font-bold ${position_summary.realized_profit >= 0 ? "text-[var(--jh-accent)]" : "text-[var(--jh-danger)]"}`}>
                      {position_summary.realized_profit >= 0 ? "+" : ""}{formatMoney(position_summary.realized_profit)}
                    </span>
                  </div>
                </div>
                {(position_summary.total_commission ?? 0) > 0 && (
                  <div className="mt-4 grid grid-cols-3 gap-3">
                    <div className="p-3 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)]">
                      <div className="text-xs text-[var(--jh-text-muted)] mb-1">累计手续费</div>
                      <div className="text-sm font-bold text-[var(--jh-text)]">{formatMoney(position_summary.total_commission!)}</div>
                    </div>
                    <div className="p-3 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)]">
                      <div className="text-xs text-[var(--jh-text-muted)] mb-1">买入佣金</div>
                      <div className="text-sm font-bold text-[var(--jh-text)]">{formatMoney(position_summary.buy_commission ?? 0)}</div>
                    </div>
                    <div className="p-3 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)]">
                      <div className="text-xs text-[var(--jh-text-muted)] mb-1">卖出佣金</div>
                      <div className="text-sm font-bold text-[var(--jh-text)]">{formatMoney(position_summary.sell_commission ?? 0)}</div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 策略版本 Tab */}
        {activeTab === "strategy" && (
          <div className="space-y-4 animate-fade-in-up">
            {strategies.length === 0 ? (
              <div className="glass-card p-8 text-center">
                <History className="w-8 h-8 text-[var(--jh-text-muted)] mx-auto mb-3" />
                <div className="text-[var(--jh-text-muted)]">暂无策略版本</div>
                <div className="text-sm text-[var(--jh-text-secondary)] mt-2">在头脑风暴室完成辩论后，策略会自动保存</div>
              </div>
            ) : (
              strategies.map((s) => {
                const content = parseStrategyContent(s.strategy_content);
                const isEditing = editingVersion === s.version_id;
                return (
                  <div key={s.version_id} className="glass-card p-5">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className={`jh-badge text-xs ${s.is_active === 1 ? "jh-badge-accent" : "jh-badge-info"}`}>V{s.version_number}</span>
                        {s.is_active === 1 && <span className="text-xs text-[var(--jh-accent)]">当前生效</span>}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-[var(--jh-text-muted)]">{formatDate(s.created_at)}</span>
                        <button type="button" onClick={() => { setEditingVersion(s.version_id); setEditContent(s.strategy_content); setStrategySaveError(""); }} className="p-1.5 rounded-lg hover:bg-[rgba(255,255,255,0.05)] text-[var(--jh-text-muted)] hover:text-[var(--jh-text)] transition-colors" aria-label="编辑策略">
                          <Edit3 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                    {isEditing ? (
                      <div className="space-y-3">
                        {(() => {
                          const preview = parseStrategyContent(editContent);
                          return preview ? (
                            <div className="p-4 rounded-lg border border-[var(--jh-border-accent)] bg-[rgba(99,230,208,0.04)]">
                              <div className="text-xs text-[var(--jh-accent)] mb-3 font-medium">预览</div>
                              <StrategyCardView content={preview} />
                            </div>
                          ) : editContent.trim() ? (
                            <p className="text-xs text-[var(--jh-warning)]">JSON 格式无效，无法预览</p>
                          ) : null;
                        })()}
                        <details className="text-xs">
                          <summary className="text-[var(--jh-text-muted)] cursor-pointer hover:text-[var(--jh-text)] mb-2">
                            编辑原始 JSON
                          </summary>
                          <textarea
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            aria-label="编辑策略内容"
                            className="w-full h-48 p-3 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)] text-[var(--jh-text)] text-xs font-mono resize-none focus:border-[var(--jh-accent)] focus:outline-none"
                          />
                        </details>
                        {strategySaveError && (
                          <p className="text-xs text-[var(--jh-danger)]">{strategySaveError}</p>
                        )}
                        <div className="flex gap-2">
                          <button type="button" onClick={handleSaveStrategy} className="jh-btn-primary flex items-center gap-1 text-xs"><Check className="w-3 h-3" />保存</button>
                          <button type="button" onClick={() => setEditingVersion(null)} className="jh-btn-secondary flex items-center gap-1 text-xs"><X className="w-3 h-3" />取消</button>
                        </div>
                      </div>
                    ) : content ? (
                      <StrategyCardView content={content} />
                    ) : <div className="text-xs text-[var(--jh-text-muted)]">策略内容解析失败</div>}
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* 交易记录 Tab */}
        {activeTab === "transactions" && (
          <div className="space-y-4 animate-fade-in-up">
            <button onClick={() => setShowTxnDialog(true)} className="w-full glass-card p-4 flex items-center justify-center gap-2 text-[var(--jh-accent)] hover:border-[var(--jh-border-accent)] transition-colors">
              <Plus className="w-5 h-5" /><span className="text-sm font-medium">录入交易记录</span>
            </button>

            {transactions.length === 0 ? (
              <div className="glass-card p-8 text-center">
                <DollarSign className="w-8 h-8 text-[var(--jh-text-muted)] mx-auto mb-3" />
                <div className="text-[var(--jh-text-muted)]">暂无交易记录</div>
                <div className="text-sm text-[var(--jh-text-secondary)] mt-2">点击上方按钮录入买入或卖出记录</div>
              </div>
            ) : (
              <div className="space-y-2">
                {transactions.map((txn) => {
                  const gross = txn.price * txn.quantity;
                  const fee =
                    commissionRate > 0 || commissionMin > 0
                      ? calcTradeCommission(gross, commissionMin, commissionRate)
                      : 0;
                  return (
                  <div key={txn.txn_id} className="glass-card p-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${txn.direction === "buy" ? "bg-[rgba(99,230,208,0.1)] text-[var(--jh-accent)]" : "bg-[rgba(255,122,122,0.1)] text-[var(--jh-danger)]"}`}>
                        {txn.direction === "buy" ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`text-sm font-semibold ${txn.direction === "buy" ? "text-[var(--jh-accent)]" : "text-[var(--jh-danger)]"}`}>{txn.direction === "buy" ? "买入" : "卖出"}</span>
                          <span className="text-sm text-[var(--jh-text)]">{txn.quantity} 股 × {formatMoney(txn.price)}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <Calendar className="w-3 h-3 text-[var(--jh-text-muted)]" />
                          <span className="text-xs text-[var(--jh-text-muted)]">{formatDate(txn.txn_time)}</span>
                          {fee > 0 && (
                            <span className="text-xs text-[var(--jh-text-muted)]">佣金 {formatMoney(fee)}</span>
                          )}
                        </div>
                        {txn.notes && <div className="text-xs text-[var(--jh-text-secondary)] mt-1">{txn.notes}</div>}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`text-base font-bold ${txn.direction === "buy" ? "text-[var(--jh-text)]" : "text-[var(--jh-accent)]"}`}>{formatMoney(gross)}</div>
                    </div>
                  </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

      </div>

      {/* 交易记录录入对话框 */}
      {showTxnDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="txn-dialog-title">
          <div className="absolute inset-0 bg-[rgba(0,0,0,0.6)] backdrop-blur-sm" onClick={() => setShowTxnDialog(false)} />
          <div className="relative w-full max-w-[440px] bg-[var(--jh-bg-2)] rounded-xl border border-[var(--jh-border)] shadow-lg max-h-[90vh] overflow-y-auto">
            <div className="p-4 border-b border-[var(--jh-border)]">
              <h3 id="txn-dialog-title" className="text-base font-semibold text-[var(--jh-text)]">录入交易记录</h3>
              <p className="text-xs text-[var(--jh-text-muted)] mt-1">交易记录一旦创建不可编辑或删除</p>
            </div>
            <div className="p-4 space-y-4">
              {needsCommissionSetup && (
                <div className="p-3 rounded-lg border border-[var(--jh-border-accent)] bg-[rgba(99,230,208,0.06)] space-y-3">
                  <div className="text-xs font-medium text-[var(--jh-accent)]">首次录入：设置佣金参数</div>
                  <p className="text-xs text-[var(--jh-text-muted)] leading-relaxed">
                    请填写您券商的单笔最低佣金和费率（万几）。本卷宗后续所有交易将按此规则计算手续费，印花税忽略不计。
                  </p>
                  <div>
                    <label className="text-xs text-[var(--jh-text-secondary)] mb-2 block">单笔最低佣金（元）</label>
                    <input
                      type="number"
                      value={txnForm.commission_min}
                      onChange={(e) => setTxnForm({ ...txnForm, commission_min: e.target.value })}
                      className="w-full p-3 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)] text-[var(--jh-text)] text-sm focus:border-[var(--jh-accent)] focus:outline-none"
                      placeholder="如 5"
                      min="0"
                      step="0.01"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-[var(--jh-text-secondary)] mb-2 block">佣金费率（万几）</label>
                    <input
                      type="number"
                      value={txnForm.commission_rate_wan}
                      onChange={(e) => setTxnForm({ ...txnForm, commission_rate_wan: e.target.value })}
                      className="w-full p-3 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)] text-[var(--jh-text)] text-sm focus:border-[var(--jh-accent)] focus:outline-none"
                      placeholder="如 2.5 表示万2.5"
                      min="0.1"
                      step="0.1"
                    />
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {[1, 1.5, 2, 2.5, 3].map((wan) => (
                        <button
                          key={wan}
                          type="button"
                          onClick={() => setTxnForm({ ...txnForm, commission_rate_wan: String(wan) })}
                          className={`px-2 py-1 text-xs rounded border transition-colors ${
                            txnForm.commission_rate_wan === String(wan)
                              ? "border-[var(--jh-accent)] text-[var(--jh-accent)] bg-[rgba(99,230,208,0.1)]"
                              : "border-[var(--jh-border)] text-[var(--jh-text-muted)] hover:border-[var(--jh-border-strong)]"
                          }`}
                        >
                          万{wan}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
              <div>
                <label className="text-xs text-[var(--jh-text-secondary)] mb-2 block">交易方向</label>
                <div className="flex gap-2">
                  <button onClick={() => setTxnForm({ ...txnForm, direction: "buy" })} className={`flex-1 p-3 rounded-lg border flex items-center justify-center gap-2 transition-colors ${txnForm.direction === "buy" ? "bg-[rgba(99,230,208,0.1)] border-[var(--jh-accent)] text-[var(--jh-accent)]" : "border-[var(--jh-border)] text-[var(--jh-text-secondary)] hover:border-[var(--jh-border-strong)]"}`}>
                    <TrendingUp className="w-4 h-4" />买入
                  </button>
                  <button onClick={() => setTxnForm({ ...txnForm, direction: "sell" })} className={`flex-1 p-3 rounded-lg border flex items-center justify-center gap-2 transition-colors ${txnForm.direction === "sell" ? "bg-[rgba(255,122,122,0.1)] border-[var(--jh-danger)] text-[var(--jh-danger)]" : "border-[var(--jh-border)] text-[var(--jh-text-secondary)] hover:border-[var(--jh-border-strong)]"}`}>
                    <TrendingDown className="w-4 h-4" />卖出
                  </button>
                </div>
              </div>
              <div>
                <label className="text-xs text-[var(--jh-text-secondary)] mb-2 block">成交价格（元）</label>
                <input type="number" value={txnForm.price} onChange={(e) => setTxnForm({ ...txnForm, price: e.target.value })} className="w-full p-3 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)] text-[var(--jh-text)] text-sm focus:border-[var(--jh-accent)] focus:outline-none" placeholder="如 1520.00" step="0.01" />
              </div>
              <div>
                <label className="text-xs text-[var(--jh-text-secondary)] mb-2 block">成交数量（股）</label>
                <input type="number" value={txnForm.quantity} onChange={(e) => setTxnForm({ ...txnForm, quantity: e.target.value })} className="w-full p-3 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)] text-[var(--jh-text)] text-sm focus:border-[var(--jh-accent)] focus:outline-none" placeholder="如 100" />
              </div>
              <div>
                <label className="text-xs text-[var(--jh-text-secondary)] mb-2 block">成交时间</label>
                <input type="datetime-local" value={txnForm.txn_time} onChange={(e) => setTxnForm({ ...txnForm, txn_time: e.target.value })} className="w-full p-3 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)] text-[var(--jh-text)] text-sm focus:border-[var(--jh-accent)] focus:outline-none" />
              </div>
              <div>
                <label className="text-xs text-[var(--jh-text-secondary)] mb-2 block">备注（可选）</label>
                <textarea value={txnForm.notes} onChange={(e) => setTxnForm({ ...txnForm, notes: e.target.value })} className="w-full p-3 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[var(--jh-border)] text-[var(--jh-text)] text-sm resize-none h-20 focus:border-[var(--jh-accent)] focus:outline-none" placeholder="记录交易原因..." />
              </div>
            </div>
            {txnError && (
              <div className="px-4 pb-2">
                <div className="p-3 rounded-lg bg-[rgba(255,122,122,0.1)] border border-[var(--jh-danger)]/30 text-sm text-[var(--jh-danger)]">
                  {txnError}
                </div>
              </div>
            )}
            <div className="p-4 border-t border-[var(--jh-border)] flex gap-2">
              <button onClick={() => { setShowTxnDialog(false); setTxnError(""); }} className="flex-1 jh-btn-secondary">取消</button>
              <button
                onClick={handleCreateTransaction}
                disabled={
                  !txnForm.price ||
                  !txnForm.quantity ||
                  txnSubmitting ||
                  (needsCommissionSetup && (!txnForm.commission_min || !txnForm.commission_rate_wan))
                }
                className="flex-1 jh-btn-primary disabled:opacity-50"
              >
                {txnSubmitting ? "提交中..." : "确认录入"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除卷宗确认 */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="delete-dialog-title">
          <div className="absolute inset-0 bg-[rgba(0,0,0,0.6)] backdrop-blur-sm" onClick={() => !deleting && setShowDeleteConfirm(false)} />
          <div className="relative w-full max-w-[400px] bg-[var(--jh-bg-2)] rounded-xl border border-[var(--jh-danger)]/30 shadow-lg p-6">
            <h3 id="delete-dialog-title" className="text-base font-semibold text-[var(--jh-text)] mb-2">确认删除卷宗？</h3>
            <p className="text-sm text-[var(--jh-text-secondary)] mb-1">
              将永久删除 <strong>{dossier.stock_name}</strong> 的策略版本、交易记录和收益数据。
            </p>
            <p className="text-xs text-[var(--jh-text-muted)] mb-6">
              此操作不可恢复。删除后可重新进入头脑风暴室，为该股票创建新卷宗。
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
                disabled={deleting}
                className="flex-1 jh-btn-secondary disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleDeleteDossier}
                disabled={deleting}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium bg-[var(--jh-danger)] text-white hover:opacity-90 disabled:opacity-50"
              >
                {deleting ? "删除中..." : "确认删除"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
