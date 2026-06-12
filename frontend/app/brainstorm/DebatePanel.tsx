'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  TrendingUp, TrendingDown, Scale,
  Loader2, MessageSquare, AlertCircle
} from 'lucide-react';
import type { Round, JudgeVerdict } from './useDebateStream';

function formatMissingInfo(missingInfo: unknown): string {
  if (missingInfo == null) return '';
  if (typeof missingInfo === 'string') return missingInfo.trim();
  if (Array.isArray(missingInfo)) {
    return missingInfo.map((item) => String(item).trim()).filter(Boolean).join('\n');
  }
  return String(missingInfo).trim();
}

function formatConfidence(confidence?: number): string {
  if (confidence == null || Number.isNaN(confidence)) return '—';
  const pct = confidence <= 1 ? confidence * 100 : confidence;
  return `${Math.round(pct)}%`;
}

interface DebatePanelProps {
  rounds: Round[];
  judgeVerdict: JudgeVerdict | null;
  isStreaming: boolean;
  streamingSide: 'bull' | 'bear' | null;
  streamingRound: number | null;
  onOpenCoach: () => void;
}

export default function DebatePanel({
  rounds,
  judgeVerdict,
  isStreaming,
  streamingSide,
  streamingRound,
  onOpenCoach,
}: DebatePanelProps) {
  if (rounds.length === 0) return null;

  return (
    <div id="debate-content-area" className="mb-6">
      {/* 策略教练按钮 */}
      {judgeVerdict && (
        <div className="flex justify-end mb-4">
          <Button
            onClick={onOpenCoach}
            className="bg-[var(--jh-accent)] text-[var(--jh-bg)] hover:bg-[var(--jh-accent-2)] flex items-center gap-2"
          >
            <MessageSquare className="w-4 h-4" />
            策略教练
          </Button>
        </div>
      )}

      {/* 三栏布局：多头-裁判-空头 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 左侧：多头观点 */}
        <Card data-knowledge-source="bull" className="bg-[var(--jh-surface)] border-[var(--jh-accent)] border-l-4 rounded-lg overflow-hidden">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2 text-[var(--jh-accent)]">
              <TrendingUp className="w-5 h-5" />
              多头观点
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[350px]">
              {rounds.map((round) => (
                <div key={round.round} className="mb-4 last:mb-0">
                  {(round.bull_content || (isStreaming && streamingSide === 'bull' && streamingRound === round.round)) && (
                    <div className="p-3 bg-[rgba(99,230,208,0.08)] rounded-lg mb-2">
                      <div className="text-xs text-[var(--jh-muted)] mb-1">第 {round.round} 轮</div>
                      <div className="text-sm text-[var(--jh-text)] debate-content">
                        {round.bull_content ? (
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{round.bull_content}</ReactMarkdown>
                        ) : (
                          <span className="text-[var(--jh-muted)]">思考中...</span>
                        )}
                        {isStreaming && streamingSide === 'bull' && streamingRound === round.round && (
                          <span className="inline-block w-1.5 h-4 bg-[var(--jh-accent)] animate-pulse ml-0.5 align-middle" />
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </ScrollArea>
          </CardContent>
        </Card>

        {/* 中间：裁判裁决 */}
        <Card
          data-knowledge-source="judge"
          className="bg-[var(--jh-surface)] border border-[rgba(245,196,81,0.22)] rounded-xl overflow-hidden shadow-[0_0_28px_rgba(245,196,81,0.05)]"
        >
          <CardHeader className="pb-3 border-b border-[var(--jh-line)] bg-[rgba(245,196,81,0.05)]">
            <CardTitle className="text-base flex items-center gap-2 text-[var(--jh-warm)]">
              <Scale className="w-5 h-5" />
              裁判裁决
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {judgeVerdict ? (
              <ScrollArea className="h-[400px] pr-3">
                <div className="space-y-4">
                  {/* 主结论：评级 + 置信度 + 质量×估值 */}
                  <div className="rounded-xl border border-[rgba(245,196,81,0.18)] bg-gradient-to-br from-[rgba(245,196,81,0.09)] to-transparent p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-[var(--jh-muted)] mb-1">投资评级</div>
                        <div className="text-4xl font-bold text-[var(--jh-warm)] tracking-tight leading-none">
                          {judgeVerdict.rating}
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-[10px] text-[var(--jh-muted)] mb-1">置信度</div>
                        <div className="text-xl font-semibold text-[var(--jh-text)] tabular-nums">
                          {formatConfidence(judgeVerdict.confidence)}
                        </div>
                      </div>
                    </div>
                    {(judgeVerdict.quality_assessment || judgeVerdict.valuation_assessment) && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {judgeVerdict.quality_assessment && (
                          <span className="inline-flex items-center rounded-full border border-[var(--jh-line)] bg-[rgba(255,255,255,0.04)] px-2.5 py-0.5 text-xs text-[var(--jh-text-secondary)]">
                            质量 · {judgeVerdict.quality_assessment}
                          </span>
                        )}
                        {judgeVerdict.valuation_assessment && (
                          <span className="inline-flex items-center rounded-full border border-[var(--jh-line)] bg-[rgba(255,255,255,0.04)] px-2.5 py-0.5 text-xs text-[var(--jh-text-secondary)]">
                            估值 · {judgeVerdict.valuation_assessment}
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* 综合研判 */}
                  {judgeVerdict.summary && (
                    <div>
                      <div className="flex items-center gap-2 mb-2.5">
                        <span className="text-xs font-semibold text-[var(--jh-warm)]">综合研判</span>
                        <div className="h-px flex-1 bg-[var(--jh-line)]" />
                      </div>
                      <p className="text-sm text-[var(--jh-text-secondary)] leading-[1.8] whitespace-pre-wrap">
                        {judgeVerdict.summary}
                      </p>
                    </div>
                  )}

                  {/* 下一步建议 */}
                  {judgeVerdict.action_hint && (
                    <div className="rounded-xl border border-[var(--jh-border-accent)] bg-[rgba(99,230,208,0.06)] p-3.5">
                      <div className="text-xs font-semibold text-[var(--jh-accent)] mb-1.5">下一步建议</div>
                      <p className="text-sm text-[var(--jh-text)] leading-relaxed">{judgeVerdict.action_hint}</p>
                    </div>
                  )}

                  {/* 信息缺口（直接展示） */}
                  {formatMissingInfo(judgeVerdict.missing_info) && (
                    <div className="rounded-xl border border-[rgba(124,184,255,0.28)] bg-[rgba(124,184,255,0.06)] p-3.5">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--jh-info)] mb-1.5">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                        信息缺口
                      </div>
                      <p className="text-sm text-[var(--jh-text-secondary)] leading-relaxed whitespace-pre-wrap">
                        {formatMissingInfo(judgeVerdict.missing_info)}
                      </p>
                    </div>
                  )}
                </div>
              </ScrollArea>
            ) : (
              <div className="h-[400px] flex items-center justify-center text-[var(--jh-muted)]">
                {isStreaming ? (
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    裁判综合评判中...
                  </div>
                ) : (
                  '裁决尚未生成'
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 右侧：空头观点 */}
        <Card data-knowledge-source="bear" className="bg-[var(--jh-surface)] border-[var(--jh-danger)] border-l-4 rounded-lg overflow-hidden">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2 text-[var(--jh-danger)]">
              <TrendingDown className="w-5 h-5" />
              空头观点
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[350px]">
              {rounds.map((round) => (
                <div key={round.round} className="mb-4 last:mb-0">
                  {(round.bear_content || (isStreaming && streamingSide === 'bear' && streamingRound === round.round)) && (
                    <div className="p-3 bg-[rgba(255,122,122,0.08)] rounded-lg mb-2">
                      <div className="text-xs text-[var(--jh-muted)] mb-1">第 {round.round} 轮</div>
                      <div className="text-sm text-[var(--jh-text)] debate-content">
                        {round.bear_content ? (
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{round.bear_content}</ReactMarkdown>
                        ) : (
                          <span className="text-[var(--jh-muted)]">思考中...</span>
                        )}
                        {isStreaming && streamingSide === 'bear' && streamingRound === round.round && (
                          <span className="inline-block w-1.5 h-4 bg-[var(--jh-danger)] animate-pulse ml-0.5 align-middle" />
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
