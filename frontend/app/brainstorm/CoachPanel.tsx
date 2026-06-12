'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Loader2, MessageSquare, X, User } from 'lucide-react';
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
  opening: '正在开场',
  chatting: '策略对话中',
  reviewing: '策略审查中',
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
  onClose,
  onSendMessage,
  onQuickReply,
  onOpenDossier,
}: CoachPanelProps) {
  const coachLoading = isCoachLoading;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="coach-panel-title"
    >
      <div
        className="w-full max-w-[560px] max-h-[85vh] h-[80vh] bg-[var(--jh-surface)] border border-[var(--jh-line)] rounded-xl shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部标题栏 */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--jh-line)] bg-[rgba(11,15,20,0.6)]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-[rgba(99,230,208,0.15)] flex items-center justify-center">
              <MessageSquare className="w-5 h-5 text-[var(--jh-accent)]" />
            </div>
            <div>
              <h3 id="coach-panel-title" className="font-medium text-[var(--jh-text)] text-sm">策略教练</h3>
              <div className="text-[10px] text-[var(--jh-muted)]">
                {COACH_STATE_LABELS[coachState] || '策略对话中'}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-[var(--jh-muted)] hover:text-[var(--jh-text)] transition-colors rounded-lg p-1.5 hover:bg-[rgba(255,255,255,0.06)]"
            aria-label="关闭策略教练"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 对话历史 */}
        <ScrollArea className="flex-1 px-4 py-4">
          <div className="space-y-4">
            {coachMessages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.role === 'coach' ? 'justify-start' : 'justify-end'}`}>
                {/* 教练头像 */}
                {msg.role === 'coach' && (
                  <div className="w-8 h-8 rounded-full bg-[rgba(99,230,208,0.15)] flex items-center justify-center flex-shrink-0 mr-2 mt-1">
                    <MessageSquare className="w-4 h-4 text-[var(--jh-accent)]" />
                  </div>
                )}
                {/* 消息气泡 */}
                <div className={`max-w-[75%] px-3.5 py-2.5 rounded-2xl ${
                  msg.role === 'coach' 
                    ? 'bg-[rgba(255,255,255,0.06)] border border-[var(--jh-line)] rounded-tl-sm' 
                    : 'bg-[rgba(99,230,208,0.12)] border border-[rgba(99,230,208,0.2)] rounded-tr-sm'
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
                  <div className="w-8 h-8 rounded-full bg-[rgba(124,184,255,0.15)] flex items-center justify-center flex-shrink-0 ml-2 mt-1">
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
                <div className="text-[var(--jh-muted)] text-sm">完成辩论后，策略教练将引导您形成投资策略</div>
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
          {/* 策略教练提示问题 */}
          {(coachSuggestedQuestions.length > 0 || canSaveCoachStrategy) && (
            <div className="flex gap-2 mb-2 overflow-x-auto">
              {canSaveCoachStrategy && (
                <button
                  onClick={() => onQuickReply('保存当前策略')}
                  className="flex-shrink-0 px-3 py-1.5 rounded-full text-xs bg-[var(--jh-accent)] text-[var(--jh-bg)] border border-[var(--jh-accent)] hover:shadow-[0_0_14px_rgba(99,230,208,0.18)] transition-all"
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
                    className="flex-shrink-0 px-3 py-1.5 rounded-full text-xs bg-[rgba(255,255,255,0.04)] text-[var(--jh-text-secondary)] border border-[var(--jh-line)] hover:bg-[rgba(99,230,208,0.08)] hover:text-[var(--jh-accent)] hover:border-[rgba(99,230,208,0.25)] transition-colors"
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
                : '回复教练...'
              }
              disabled={coachLoading || coachMessages.length === 0}
              className="flex-1 bg-[rgba(255,255,255,0.04)] border border-[var(--jh-line)] text-sm text-[var(--jh-text)] placeholder:text-[var(--jh-weak)] focus:border-[rgba(99,230,208,0.3)] rounded-xl"
            />
            <Button
              onClick={onSendMessage}
              disabled={coachLoading || !coachInput.trim()}
              size="sm"
              className="bg-[var(--jh-accent)] text-[var(--jh-bg)] rounded-xl px-5 hover:shadow-[0_0_15px_rgba(99,230,208,0.15)]"
            >
              发送
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
