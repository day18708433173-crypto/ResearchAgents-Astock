'use client';

import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  TrendingUp, TrendingDown, Scale,
  Loader2, MessageSquare, AlertCircle
} from 'lucide-react';
import type { Round, JudgeVerdict, DebatePhase } from './useDebateStream';

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

function DebateSideContent({
  content,
  isLive,
  side,
}: {
  content: string;
  isLive: boolean;
  side: 'bull' | 'bear';
}) {
  const cursorClass = side === 'bull' ? 'bg-[var(--jh-accent)]' : 'bg-[var(--jh-danger)]';

  if (!content && isLive) {
    return (
      <span className="text-[var(--jh-muted)] inline-flex items-center gap-2">
        思考中...
        <span className={`inline-block w-1.5 h-4 ${cursorClass} animate-pulse`} />
      </span>
    );
  }

  if (!content) return null;

  if (isLive) {
    return (
      <p className="whitespace-pre-wrap break-words leading-relaxed">
        {content}
        <span className={`inline-block w-1.5 h-4 ${cursorClass} animate-pulse ml-0.5 align-middle`} />
      </p>
    );
  }

  return (
    <div className="debate-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}

interface DebatePanelProps {
  rounds: Round[];
  judgeVerdict: JudgeVerdict | null;
  isStreaming: boolean;
  streamingSide: 'bull' | 'bear' | null;
  streamingRound: number | null;
  statusMessage?: string;
  onOpenCoach: () => void;
  coachActive?: boolean;
  phase?: DebatePhase;
}

export default function DebatePanel({
  rounds,
  judgeVerdict,
  isStreaming,
  streamingSide,
  streamingRound,
  statusMessage = '',
  onOpenCoach,
  coachActive = false,
  phase,
}: DebatePanelProps) {
  const bullScrollRef = useRef<HTMLDivElement>(null);
  const bearScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isStreaming || !streamingSide) return;
    const el = streamingSide === 'bull' ? bullScrollRef.current : bearScrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [rounds, isStreaming, streamingSide, streamingRound]);

  if (rounds.length === 0 && !isStreaming) return null;

  const placeholderRound = rounds.length === 0 && isStreaming;

  return (
    <div id="debate-content-area" className="mb-6">
      {judgeVerdict && phase === 'done' && !coachActive && (
        <div className="flex justify-end mb-4">
          <Button
            onClick={onOpenCoach}
            className="bg-[var(--jh-accent)] text-[var(--jh-bg)] hover:bg-[var(--jh-accent-2)] flex items-center gap-2"
          >
            <MessageSquare className="w-4 h-4" />
            策略审查
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 多头 */}
        <Card data-knowledge-source="bull" className="bg-[var(--jh-surface)] border-[var(--jh-line)] border-l-4 border-l-[var(--jh-accent)] rounded-lg overflow-hidden shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2 text-[var(--jh-text)]">
              <TrendingUp className="w-5 h-5" />
              多头研究纪要
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div ref={bullScrollRef} className="h-[350px] overflow-y-auto pr-3">
                {placeholderRound ? (
                  <div className="p-3 text-sm text-[var(--jh-muted)] flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin shrink-0" />
                    {statusMessage || '正在准备辩论...'}
                  </div>
                ) : (
                  rounds.map((round) => {
                    const isLiveBull = isStreaming && streamingSide === 'bull' && streamingRound === round.round;
                    const showBull = round.bull_content || isLiveBull;
                    if (!showBull) return null;
                    return (
                      <div key={round.round} className="mb-4 last:mb-0">
                        <div className="p-3 bg-[var(--jh-bg-2)] rounded-md border border-[var(--jh-line)] mb-2">
                          <div className="text-xs text-[var(--jh-muted)] mb-1">第 {round.round} 轮</div>
                          <div className="text-sm text-[var(--jh-text)]">
                            <DebateSideContent
                              content={round.bull_content}
                              isLive={isLiveBull}
                              side="bull"
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
            </div>
          </CardContent>
        </Card>

        {/* 裁判 */}
        <Card
          data-knowledge-source="judge"
          className="bg-[var(--jh-surface)] border border-[var(--jh-line)] rounded-lg overflow-hidden shadow-none"
        >
          <CardHeader className="pb-3 border-b border-[var(--jh-line)] bg-[var(--jh-bg-2)]">
            <CardTitle className="text-base flex items-center gap-2 text-[var(--jh-text)]">
              <Scale className="w-5 h-5" />
              裁决摘要
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {judgeVerdict ? (
              <ScrollArea className="h-[400px] pr-3">
                <div className="space-y-4">
                  <div className="rounded-md border border-[var(--jh-line)] bg-[var(--jh-bg-2)] p-4">
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
                          <span className="inline-flex items-center rounded-sm border border-[var(--jh-line)] bg-[rgba(255,255,255,0.04)] px-2.5 py-0.5 text-xs text-[var(--jh-text-secondary)]">
                            质量 · {judgeVerdict.quality_assessment}
                          </span>
                        )}
                        {judgeVerdict.valuation_assessment && (
                          <span className="inline-flex items-center rounded-sm border border-[var(--jh-line)] bg-[rgba(255,255,255,0.04)] px-2.5 py-0.5 text-xs text-[var(--jh-text-secondary)]">
                            估值 · {judgeVerdict.valuation_assessment}
                          </span>
                        )}
                      </div>
                    )}
                  </div>

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

                  {judgeVerdict.action_hint && (
                    <div className="rounded-md border border-[var(--jh-border-accent)] bg-[rgba(143,212,195,0.06)] p-3.5">
                      <div className="text-xs font-semibold text-[var(--jh-accent)] mb-1.5">下一步建议</div>
                      <p className="text-sm text-[var(--jh-text)] leading-relaxed">{judgeVerdict.action_hint}</p>
                    </div>
                  )}

                  {formatMissingInfo(judgeVerdict.missing_info) && (
                    <div className="rounded-md border border-[rgba(134,167,213,0.28)] bg-[rgba(134,167,213,0.06)] p-3.5">
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
                {phase === 'judging' || isStreaming ? (
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {phase === 'judging' ? '裁决摘要生成中...' : '等待裁决...'}
                  </div>
                ) : (
                  '裁决摘要尚未生成'
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 空头 */}
        <Card data-knowledge-source="bear" className="bg-[var(--jh-surface)] border-[var(--jh-line)] border-l-4 border-l-[var(--jh-danger)] rounded-lg overflow-hidden shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2 text-[var(--jh-text)]">
              <TrendingDown className="w-5 h-5" />
              空头研究纪要
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div ref={bearScrollRef} className="h-[350px] overflow-y-auto pr-3">
                {placeholderRound ? (
                  <div className="p-3 text-sm text-[var(--jh-muted)] flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin shrink-0" />
                    {statusMessage || '正在准备辩论...'}
                  </div>
                ) : (
                  rounds.map((round) => {
                    const isLiveBear = isStreaming && streamingSide === 'bear' && streamingRound === round.round;
                    const showBear = round.bear_content || isLiveBear;
                    if (!showBear) return null;
                    return (
                      <div key={round.round} className="mb-4 last:mb-0">
                        <div className="p-3 bg-[var(--jh-bg-2)] rounded-md border border-[var(--jh-line)] mb-2">
                          <div className="text-xs text-[var(--jh-muted)] mb-1">第 {round.round} 轮</div>
                          <div className="text-sm text-[var(--jh-text)]">
                            <DebateSideContent
                              content={round.bear_content}
                              isLive={isLiveBear}
                              side="bear"
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
