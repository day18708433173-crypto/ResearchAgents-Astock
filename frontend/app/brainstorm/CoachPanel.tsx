'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Loader2, MessageSquare, StickyNote, X, User } from 'lucide-react';
import ResearchNoteEditor from '@/components/ResearchNoteEditor';
import type { JudgeVerdict } from './useDebateStream';

// 策略教练对话消息
export interface CoachMessage {
  role: 'coach' | 'user';
  content: string;
  timestamp: Date;
}

// 教练状态类型（与后端状态机对齐）
export type CoachState = 'opening' | 'chatting' | 'reviewing' | 'confirming' | 'done';

export const COACH_STATE_LABELS: Record<CoachState, string> = {
  opening: '准备审查',
  chatting: '审查进行中',
  reviewing: '策略校验中',
  confirming: '确认保存',
  done: '策略已保存',
};

interface CoachPanelProps {
  coachMessages: CoachMessage[];
  coachInput: string;
  onCoachInputChange: (value: string) => void;
  isCoachLoading: boolean;
  coachState: CoachState;
  coachSuggestedQuestions: string[];
  canSaveCoachStrategy: boolean;
  savedCoachDossierId: number | null;
  debateResult: JudgeVerdict | null;
  stockCode?: string;
  stockName?: string;
  onClose: () => void;
  onSendMessage: () => void;
  onQuickReply: (text: string) => void;
  onOpenDossier: (dossierId: number) => void;
}

export default function CoachPanel({
  coachMessages,
  coachInput,
  onCoachInputChange,
  isCoachLoading,
  coachState,
  coachSuggestedQuestions,
  canSaveCoachStrategy,
  savedCoachDossierId,
  debateResult,
  stockCode,
  stockName,
  onClose,
  onSendMessage,
  onQuickReply,
  onOpenDossier,
}: CoachPanelProps) {
  const coachLoading = isCoachLoading;

  return (
    <div
      className="fixed inset-0 z-[60] flex justify-end bg-black/35"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="coach-panel-title"
    >
      <div
        className="h-full w-full max-w-[min(960px,100vw)] flex flex-col sm:flex-row overflow-hidden border-l border-[var(--jh-line)] bg-[var(--jh-surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 策略审查对话 */}
        <div className="flex min-h-0 min-w-0 w-full max-w-[560px] flex-1 flex-col overflow-hidden">
        {/* 顶部标题栏 */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--jh-line)] bg-[var(--jh-bg-2)]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-md bg-[rgba(143,212,195,0.10)] border border-[var(--jh-border-accent)] flex items-center justify-center">
              <MessageSquare className="w-5 h-5 text-[var(--jh-accent)]" />
            </div>
            <div>
              <h3 id="coach-panel-title" className="font-medium text-[var(--jh-text)] text-sm">策略审查</h3>
              <div className="text-[10px] text-[var(--jh-muted)]">
                {COACH_STATE_LABELS[coachState] || '审查进行中'}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-[var(--jh-muted)] hover:text-[var(--jh-text)] transition-colors rounded-lg p-1.5 hover:bg-[rgba(255,255,255,0.06)]"
            aria-label="关闭策略审查"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 对话历史 */}
        <ScrollArea className="flex-1 px-4 py-4">
          <div className="space-y-4">
            {coachMessages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.role === 'coach' ? 'justify-start' : 'justify-end'}`}>
                {/* 审查方标记 */}
                {msg.role === 'coach' && (
                  <div className="w-8 h-8 rounded-md bg-[rgba(143,212,195,0.10)] border border-[var(--jh-border-accent)] flex items-center justify-center flex-shrink-0 mr-2 mt-1">
                    <MessageSquare className="w-4 h-4 text-[var(--jh-accent)]" />
                  </div>
                )}
                {/* 消息气泡 */}
                <div className={`max-w-[82%] px-3.5 py-2.5 rounded-md ${
                  msg.role === 'coach' 
                    ? 'bg-[rgba(255,255,255,0.05)] border border-[var(--jh-line)]'
                    : 'bg-[rgba(143,212,195,0.10)] border border-[rgba(143,212,195,0.22)]'
                }`}>
                  <div className="text-sm text-[var(--jh-text)] coach-content leading-relaxed">
                    {msg.content ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    ) : (
                      isCoachLoading && idx === coachMessages.length - 1 && (
                        <span className="text-[var(--jh-muted)]">思考中...</span>
                      )
                    )}
                    {isCoachLoading && msg.role === 'coach' && idx === coachMessages.length - 1 && msg.content && (
                      <span className="inline-block w-1.5 h-4 bg-[var(--jh-accent)] animate-pulse ml-0.5 align-middle" />
                    )}
                  </div>
                </div>
                {/* 用户头像 */}
                {msg.role !== 'coach' && (
                  <div className="w-8 h-8 rounded-md bg-[rgba(134,167,213,0.12)] border border-[rgba(134,167,213,0.24)] flex items-center justify-center flex-shrink-0 ml-2 mt-1">
                    <User className="w-4 h-4 text-[var(--jh-info)]" />
                  </div>
                )}
              </div>
            ))}
            
            {/* 空态 */}
            {coachMessages.length === 0 && !debateResult && (
              <div className="text-center py-12">
                <div className="w-16 h-16 rounded-full bg-[rgba(99,230,208,0.1)] flex items-center justify-center mx-auto mb-3">
                  <MessageSquare className="w-8 h-8 text-[var(--jh-accent)]" />
                </div>
                <div className="text-[var(--jh-muted)] text-sm">完成研究纪要后，策略审查将帮助形成投资策略</div>
              </div>
            )}
            
            {/* 输入等待态 */}
            {coachMessages.length === 0 && debateResult && coachLoading && (
              <div className="flex items-center justify-center p-4">
                <Loader2 className="w-4 h-4 animate-spin text-[var(--jh-accent)]" />
              </div>
            )}
          </div>
        </ScrollArea>

        {/* 底部输入区域 */}
        <div className="px-4 py-3 border-t border-[var(--jh-line)] bg-[rgba(11,15,20,0.5)]">
          {savedCoachDossierId && coachState === 'done' && (
            <button
              type="button"
              onClick={() => onOpenDossier(savedCoachDossierId)}
              className="w-full mb-2 text-xs text-[var(--jh-accent)] hover:underline text-left"
            >
              策略已写入卷宗，点击查看 →
            </button>
          )}
          {/* 策略审查提示问题 */}
          {(coachSuggestedQuestions.length > 0 || canSaveCoachStrategy) && (
            <div className="flex gap-2 mb-2 overflow-x-auto">
              {canSaveCoachStrategy && (
                <button
                  onClick={() => onQuickReply('保存当前策略')}
                  className="flex-shrink-0 px-3 py-1.5 rounded-sm text-xs bg-[var(--jh-accent)] text-[var(--jh-bg)] border border-[var(--jh-accent)] transition-colors"
                >
                  保存当前策略
                </button>
              )}
              {coachSuggestedQuestions
                .filter((question) => question !== '保存当前策略' || !canSaveCoachStrategy)
                .map((question) => (
                  <button
                    key={question}
                    onClick={() => onQuickReply(question)}
                    className="flex-shrink-0 px-3 py-1.5 rounded-sm text-xs bg-[rgba(255,255,255,0.04)] text-[var(--jh-text-secondary)] border border-[var(--jh-line)] hover:bg-[rgba(143,212,195,0.08)] hover:text-[var(--jh-accent)] hover:border-[rgba(143,212,195,0.25)] transition-colors"
                  >
                    {question}
                  </button>
                ))}
            </div>
          )}
          <div className="flex gap-2">
            <Input
              value={coachInput}
              onChange={(e) => onCoachInputChange(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && coachInput.trim() && !coachLoading) { e.preventDefault(); onSendMessage(); } }}
              placeholder={
                coachState === 'opening' ? '发送消息开始...' 
                : coachState === 'reviewing' ? '回复「确认保存」...'
                : coachState === 'done' ? '继续交流...'
                : '补充策略约束...'
              }
              disabled={coachLoading || coachMessages.length === 0}
              className="flex-1 bg-[rgba(255,255,255,0.04)] border border-[var(--jh-line)] text-sm text-[var(--jh-text)] placeholder:text-[var(--jh-weak)] focus:border-[rgba(143,212,195,0.35)] rounded-md"
            />
            <Button
              onClick={onSendMessage}
              disabled={coachLoading || !coachInput.trim()}
              size="sm"
              className="bg-[var(--jh-accent)] text-[var(--jh-bg)] rounded-md px-5"
            >
              发送
            </Button>
          </div>
        </div>
        </div>

        {/* 研究笔记：与策略审查并排，便于对照编辑 */}
        <aside className="flex h-[min(38vh,320px)] sm:h-full w-full sm:w-[min(380px,38vw)] shrink-0 flex-col overflow-hidden border-t sm:border-t-0 border-l-0 sm:border-l border-[var(--jh-line)] bg-[var(--jh-bg-2)]">
          <div className="flex items-center justify-between border-b border-[var(--jh-line)] px-4 py-3">
            <div className="flex items-center gap-2">
              <StickyNote className="w-4 h-4 text-[var(--jh-text-muted)]" />
              <h3 className="text-sm font-medium text-[var(--jh-text)]">研究笔记</h3>
            </div>
            {stockCode && (
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--jh-text-muted)]">
                {stockCode}
              </span>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            {stockCode && stockName ? (
              <ResearchNoteEditor
                stockCode={stockCode}
                stockName={stockName}
                variant="coach"
              />
            ) : (
              <div className="p-4 text-sm text-[var(--jh-text-muted)]">
                选择标的后，可在此记录假设与待验证事项，并与策略审查对照。
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
