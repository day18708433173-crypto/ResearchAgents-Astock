'use client';

import { useEffect, useRef, useState } from 'react';

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
  data?: any;
  round?: number;
  content?: string;
  delta?: string;
}

export interface DataCardFieldInfo {
  value: any;
  grade: string;
  source: string;
  as_of?: string;
  period_label?: string;
  period_warning?: string;
}

interface UseDebateStreamOptions {
  /** 辩论启动时调用（用于重置教练等外部状态） */
  onDebateStart?: () => void;
  /** 辩论完成时调用（用于刷新历史记录等） */
  onComplete?: () => void;
  toast: (message: string, type?: 'success' | 'error' | 'info') => void;
}

export function useDebateStream({ onDebateStart, onComplete, toast }: UseDebateStreamOptions) {
  const debateAbortRef = useRef<AbortController | null>(null);

  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingSide, setStreamingSide] = useState<'bull' | 'bear' | null>(null);
  const [streamingRound, setStreamingRound] = useState<number | null>(null);
  const [rounds, setRounds] = useState<Round[]>([]);
  const [judgeVerdict, setJudgeVerdict] = useState<JudgeVerdict | null>(null);
  const [statusMessage, setStatusMessage] = useState('');
  const [coverage, setCoverage] = useState(0);
  const [dataCardFields, setDataCardFields] = useState<Record<string, DataCardFieldInfo>>({});
  const [currentDebateId, setCurrentDebateId] = useState<number | null>(null);

  useEffect(() => {
    return () => {
      debateAbortRef.current?.abort();
    };
  }, []);

  // 开始辩论（流式输出）
  const startDebate = async (selectedStock: Stock | null) => {
    if (!selectedStock) return;

    debateAbortRef.current?.abort();
    const abortController = new AbortController();
    debateAbortRef.current = abortController;

    setIsStreaming(true);
    setStreamingSide(null);
    setStreamingRound(null);
    setRounds([]);
    setJudgeVerdict(null);
    setStatusMessage('正在准备...');
    setCoverage(0);
    setCurrentDebateId(null);
    onDebateStart?.();

    const params = new URLSearchParams({
      ticker: selectedStock.ts_code,
      ticker_name: selectedStock.name,
    });

    const streamUrl = `/api/debate/stream?${params.toString()}`;

    try {
      const response = await fetch(streamUrl, { signal: abortController.signal });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('无法获取流读取器');
      }

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
            const jsonStr = line.slice(6);
            try {
              const data: SSEEvent = JSON.parse(jsonStr);

              switch (data.type) {
                case 'status':
                  setStatusMessage(data.message || '');
                  break;

                case 'data_card':
                  setCoverage(data.data?.coverage || 0);
                  if (data.data?.fields) {
                    setDataCardFields(data.data.fields);
                  }
                  break;

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

                case 'judge':
                  setJudgeVerdict(data.data || null);
                  break;

                case 'complete':
                  if (data.data?.debate_id) {
                    setCurrentDebateId(Number(data.data.debate_id));
                  }
                  setStatusMessage('辩论完成！进入 Step 3 与策略教练制定策略');
                  setIsStreaming(false);
                  setStreamingSide(null);
                  setStreamingRound(null);
                  onComplete?.();
                  break;

                case 'error':
                  setStatusMessage(`错误: ${data.message}`);
                  toast(data.message || '辩论出错', 'error');
                  setIsStreaming(false);
                  setStreamingSide(null);
                  setStreamingRound(null);
                  break;
              }
            } catch (e) {
              console.error('解析事件失败:', e, jsonStr);
            }
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        setStatusMessage('已停止辩论');
        return;
      }
      console.error('[ERROR] SSE连接失败:', err);
      const msg = err instanceof Error ? err.message : String(err);
      setStatusMessage(`连接中断: ${msg}`);
      toast('辩论连接中断，请重试', 'error');
    } finally {
      if (debateAbortRef.current === abortController) {
        setIsStreaming(false);
        setStreamingSide(null);
        setStreamingRound(null);
        debateAbortRef.current = null;
      }
    }
  };

  const stopDebate = () => {
    debateAbortRef.current?.abort();
    debateAbortRef.current = null;
    setIsStreaming(false);
    setStreamingSide(null);
    setStreamingRound(null);
    setStatusMessage('已停止');
  };

  return {
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
    startDebate,
    stopDebate,
  };
}
