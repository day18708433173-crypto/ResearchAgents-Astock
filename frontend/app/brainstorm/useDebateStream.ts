'use client';

import { useEffect, useRef, useState } from 'react';
import { buildUserLlmHeaders } from '@/lib/llmConfig';

// 类型定义
export interface Stock {
  ts_code: string;
  name: string;
  code: string;
  price: number;
  industry: string;
}

export interface Round {
  round: number;
  bull_content: string;
  bear_content: string;
}

export interface JudgeVerdict {
  rating: string;
  confidence?: number;
  summary: string;
  quality_assessment?: string;
  valuation_assessment?: string;
  bull_strengths?: string[];
  bear_strengths?: string[];
  bull_weaknesses?: string[];
  bear_weaknesses?: string[];
  key_risk?: string;
  key_opportunity?: string;
  missing_info?: string | string[];
  action_hint?: string;
}

interface SSEEvent {
  type: string;
  message?: string;
  data?: unknown;
  round?: number;
  content?: string;
  delta?: string;
  debate_id?: number;
  max_rounds_suggested?: number;
}

export interface DataCardFieldInfo {
  value: unknown;
  grade: string;
  source: string;
  as_of?: string;
  period_label?: string;
  period_warning?: string;
}

interface DataCardPayload {
  coverage?: number;
  fields?: Record<string, DataCardFieldInfo>;
  debate_id?: unknown;
}

/** 辩论阶段状态机 */
export type DebatePhase =
  | 'idle'            // 未开始
  | 'streaming'       // 正在流式生成（一轮或裁判）
  | 'paused'          // 轮次完成，等待用户决定继续/裁决
  | 'judging'         // 裁判阶段流式生成中
  | 'done';           // 裁判完成

interface UseDebateStreamOptions {
  onDebateStart?: () => void;
  onRoundComplete?: (round: number, debateId: number) => void;
  onComplete?: () => void;
  toast: (message: string, type?: 'success' | 'error' | 'info') => void;
}

export function useDebateStream({ onDebateStart, onRoundComplete, onComplete, toast }: UseDebateStreamOptions) {
  const abortRef = useRef<AbortController | null>(null);

  const [phase, setPhase] = useState<DebatePhase>('idle');
  const [streamingSide, setStreamingSide] = useState<'bull' | 'bear' | null>(null);
  const [streamingRound, setStreamingRound] = useState<number | null>(null);
  const [rounds, setRounds] = useState<Round[]>([]);
  const [judgeVerdict, setJudgeVerdict] = useState<JudgeVerdict | null>(null);
  const [statusMessage, setStatusMessage] = useState('');
  const [coverage, setCoverage] = useState(0);
  const [dataCardFields, setDataCardFields] = useState<Record<string, DataCardFieldInfo>>({});
  const [currentDebateId, setCurrentDebateId] = useState<number | null>(null);
  const [currentRoundNum, setCurrentRoundNum] = useState(0);
  const [maxRoundsSuggested, setMaxRoundsSuggested] = useState(3);

  /** 派生：是否正在流式输出（round 或 judge） */
  const isStreaming = phase === 'streaming' || phase === 'judging';

  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  // ─── 内部：消费一个 SSE 流 ────────────────────────────
  const _consumeStream = async (
    url: string,
    onEvent: (ev: SSEEvent) => void,
  ): Promise<void> => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const response = await fetch(url, {
      signal: controller.signal,
      headers: buildUserLlmHeaders(),
    });

    if (!response.ok) {
      const txt = await response.text();
      throw new Error(`HTTP ${response.status}: ${txt}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('无法获取流读取器');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const ev: SSEEvent = JSON.parse(line.slice(6));
            onEvent(ev);
          } catch (e) {
            console.error('解析事件失败:', e, line.slice(6));
          }
        }
      }
    }
  };

  // ─── 开始第一轮（创建新辩论） ───────────────────────────
  const startFirstRound = async (
    stock: Stock,
    focusQuestion: string = '',
  ) => {
    abortRef.current?.abort();
    setPhase('streaming');
    setStreamingSide(null);
    setStreamingRound(null);
    setRounds([]);
    setJudgeVerdict(null);
    setStatusMessage('正在准备...');
    setCoverage(0);
    setDataCardFields({});
    setCurrentDebateId(null);
    setCurrentRoundNum(0);
    onDebateStart?.();

    const params = new URLSearchParams({
      ticker: stock.ts_code,
      ticker_name: stock.name,
      round_num: '1',
      focus_question: focusQuestion,
    });

    try {
      await _consumeStream(`/api/debate/round?${params}`, (ev) => {
        _handleRoundEvent(ev);
      });
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        setStatusMessage('已停止');
        setPhase('idle');
        return;
      }
      console.error('[ERROR] 第1轮SSE失败:', err);
      toast('连接中断，请重试', 'error');
      setPhase('idle');
    } finally {
      if (abortRef.current?.signal.aborted) {
        abortRef.current = null;
      }
    }
  };

  // ─── 继续下一轮 ────────────────────────────────────────
  const continueNextRound = async (
    stock: Stock,
    debateId: number,
    nextRoundNum: number,
    focusQuestion: string = '',
  ) => {
    abortRef.current?.abort();
    setPhase('streaming');
    setStreamingSide(null);
    setStreamingRound(null);
    setStatusMessage('正在准备下一轮...');

    const params = new URLSearchParams({
      ticker: stock.ts_code,
      ticker_name: stock.name,
      round_num: String(nextRoundNum),
      debate_id: String(debateId),
      focus_question: focusQuestion,
    });

    try {
      await _consumeStream(`/api/debate/round?${params}`, (ev) => {
        _handleRoundEvent(ev);
      });
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        setStatusMessage('已停止');
        setPhase('paused');
        return;
      }
      console.error('[ERROR] 续轮SSE失败:', err);
      toast('连接中断，请重试', 'error');
      setPhase('paused');
    } finally {
      if (abortRef.current?.signal.aborted) {
        abortRef.current = null;
      }
    }
  };

  // ─── 请求裁判裁决 ──────────────────────────────────────
  const requestJudge = async (
    stock: Stock,
    debateId: number,
    focusQuestion: string = '',
  ) => {
    abortRef.current?.abort();
    setPhase('judging');
    setStatusMessage('裁判综合评判中...');

    const params = new URLSearchParams({
      ticker: stock.ts_code,
      ticker_name: stock.name,
      debate_id: String(debateId),
      focus_question: focusQuestion,
    });

    try {
      await _consumeStream(`/api/debate/judge?${params}`, (ev) => {
        switch (ev.type) {
          case 'status':
            setStatusMessage(ev.message || '');
            break;
          case 'judge':
            setJudgeVerdict((ev.data as JudgeVerdict) || null);
            break;
          case 'complete':
            setPhase('done');
            setStatusMessage('研究纪要已完成');
            onComplete?.();
            break;
          case 'error':
            setStatusMessage(`裁判错误: ${ev.message}`);
            toast(ev.message || '裁判失败', 'error');
            setPhase('paused');
            break;
        }
      });
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        setStatusMessage('已停止');
        setPhase('paused');
        return;
      }
      console.error('[ERROR] 裁判SSE失败:', err);
      toast('裁判连接中断，请重试', 'error');
      setPhase('paused');
    } finally {
      if (abortRef.current?.signal.aborted) {
        abortRef.current = null;
      }
    }
  };

  // ─── 处理轮次 SSE 事件 ─────────────────────────────────
  const _handleRoundEvent = (data: SSEEvent) => {
    switch (data.type) {
      case 'status':
        setStatusMessage(data.message || '');
        break;

      case 'data_card':
      case 'data_card_update': {
        const payload = (data.data || {}) as DataCardPayload;
        if (payload.coverage != null) setCoverage(payload.coverage);
        if (payload.fields) setDataCardFields(payload.fields);
        break;
      }

      case 'round_start':
        setStatusMessage(`第 ${data.round} 轮辩论开始`);
        setRounds(prev => {
          const roundNum = data.round || 1;
          if (prev.find(r => r.round === roundNum)) return prev;
          return [...prev, { round: roundNum, bull_content: '', bear_content: '' }];
        });
        break;

      case 'bull_token':
        setStreamingSide('bull');
        setStreamingRound(data.round ?? null);
        setRounds(prev => {
          const roundNum = data.round || 1;
          const existing = prev.find(r => r.round === roundNum);
          if (existing) {
            return prev.map(r =>
              r.round === roundNum
                ? { ...r, bull_content: (r.bull_content || '') + (data.delta || '') }
                : r
            );
          }
          return [...prev, { round: roundNum, bull_content: data.delta || '', bear_content: '' }];
        });
        break;

      case 'bear_token':
        setStreamingSide('bear');
        setStreamingRound(data.round ?? null);
        setRounds(prev => {
          const roundNum = data.round || 1;
          const existing = prev.find(r => r.round === roundNum);
          if (existing) {
            return prev.map(r =>
              r.round === roundNum
                ? { ...r, bear_content: (r.bear_content || '') + (data.delta || '') }
                : r
            );
          }
          return [...prev, { round: roundNum, bull_content: '', bear_content: data.delta || '' }];
        });
        break;

      case 'bull_speak':
        setStreamingSide(prev => (prev === 'bull' ? null : prev));
        setRounds(prev => {
          const existing = prev.find(r => r.round === data.round);
          if (existing) {
            return prev.map(r => r.round === data.round ? { ...r, bull_content: data.content || '' } : r);
          }
          return [...prev, { round: data.round || 1, bull_content: data.content || '', bear_content: '' }];
        });
        break;

      case 'bear_speak':
        setStreamingSide(prev => (prev === 'bear' ? null : prev));
        setRounds(prev => {
          const existing = prev.find(r => r.round === data.round);
          if (existing) {
            return prev.map(r => r.round === data.round ? { ...r, bear_content: data.content || '' } : r);
          }
          return [...prev, { round: data.round || 1, bull_content: '', bear_content: data.content || '' }];
        });
        break;

      case 'round_complete': {
        const debateId = data.debate_id ?? null;
        const completedRound = data.round || 1;
        if (debateId) setCurrentDebateId(debateId);
        setCurrentRoundNum(completedRound);
        if (data.max_rounds_suggested) setMaxRoundsSuggested(data.max_rounds_suggested);
        setStreamingSide(null);
        setStreamingRound(null);
        setPhase('paused');
        setStatusMessage(`第 ${completedRound} 轮完成，可继续辩论或直接请求裁决`);
        if (debateId) onRoundComplete?.(completedRound, debateId);
        break;
      }

      case 'error':
        setStatusMessage(`错误: ${data.message}`);
        toast(data.message || '生成出错', 'error');
        setPhase(prev => (prev === 'streaming' ? 'idle' : prev));
        setStreamingSide(null);
        setStreamingRound(null);
        break;
    }
  };

  const stopDebate = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreamingSide(null);
    setStreamingRound(null);
    if (phase === 'streaming') {
      setPhase(currentRoundNum > 0 ? 'paused' : 'idle');
    } else if (phase === 'judging') {
      setPhase('paused');
    }
    setStatusMessage('已停止');
  };

  const resetDebate = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setPhase('idle');
    setStreamingSide(null);
    setStreamingRound(null);
    setRounds([]);
    setJudgeVerdict(null);
    setStatusMessage('');
    setCoverage(0);
    setDataCardFields({});
    setCurrentDebateId(null);
    setCurrentRoundNum(0);
  };

  return {
    phase,
    isStreaming,
    streamingSide,
    streamingRound,
    rounds,
    setRounds,
    judgeVerdict,
    setJudgeVerdict,
    statusMessage,
    setStatusMessage,
    coverage,
    setCoverage,
    dataCardFields,
    setDataCardFields,
    currentDebateId,
    setCurrentDebateId,
    currentRoundNum,
    maxRoundsSuggested,
    startFirstRound,
    continueNextRound,
    requestJudge,
    stopDebate,
    resetDebate,
  };
}
