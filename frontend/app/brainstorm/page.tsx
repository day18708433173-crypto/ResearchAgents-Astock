'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { 
  Search, Sparkles, Scale, 
  Loader2,
  MessageSquare, X, BookOpen, Clock
} from 'lucide-react';
import {
  askKnowledge,
  streamCoachChat,
  type CoachStreamEvent,
  type KnowledgeMessage as ApiKnowledgeMessage,
} from '@/lib/api';
import { useToast } from '@/components/toast-provider';
import { useDebateStream, type Stock, type JudgeVerdict } from './useDebateStream';
import DebatePanel from './DebatePanel';
import CoachPanel, { type CoachMessage, type CoachState } from './CoachPanel';

interface DebateHistoryItem {
  id: number;
  ticker: string;
  ticker_name: string;
  coverage?: number;
  rating?: string;
  summary?: string;
  rounds_count?: number;
  created_at: string;
}

interface DebateHistoryDetail {
  id: number;
  ticker: string;
  ticker_name: string;
  coverage?: number;
  rounds: Array<{
    round: number;
    bull?: string;
    bear?: string;
    bull_content?: string;
    bear_content?: string;
  }>;
  data_card?: {
    coverage?: number;
    fields?: Record<string, { value: unknown; grade: string; source: string; as_of?: string; period_label?: string; period_warning?: string }>;
  } | null;
  judge_verdict?: JudgeVerdict | null;
  coach_messages?: Array<{
    role: 'coach' | 'user';
    content: string;
    timestamp?: string;
  }>;
  created_at: string;
}

const LOCAL_DEBATE_HISTORY_KEY = 'jingheng_debate_history';

/** 数据库自增 ID；本地兜底曾误用 Date.now() 作为 ID */
const isRealDebateId = (id: number) => id > 0 && id < 1_000_000_000_000;

const readLocalDebateHistory = (): DebateHistoryItem[] => {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(LOCAL_DEBATE_HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((item) => isRealDebateId(item?.id)) : [];
  } catch {
    return [];
  }
};

const writeLocalDebateHistory = (items: DebateHistoryItem[]) => {
  if (typeof window === 'undefined') return;
  const valid = items.filter((item) => isRealDebateId(item.id));
  window.localStorage.setItem(LOCAL_DEBATE_HISTORY_KEY, JSON.stringify(valid.slice(0, 12)));
};

const mergeDebateHistory = (...groups: DebateHistoryItem[][]): DebateHistoryItem[] => {
  const byId = new Map<number, DebateHistoryItem>();
  for (const item of groups.flat().filter(Boolean)) {
    if (!item.ticker || !isRealDebateId(item.id)) continue;
    byId.set(item.id, item);
  }
  return Array.from(byId.values()).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
};

const fetchDebateHistory = async (limit = 6): Promise<DebateHistoryItem[]> => {
  const res = await fetch(`/api/debate/history?limit=${limit}`, { cache: 'no-store' });
  if (!res.ok) return [];
  const data = await res.json();
  return Array.isArray(data) ? data.filter((item) => isRealDebateId(item?.id)) : [];
};

const saveCoachTranscript = async (debateId: number | null, messages: CoachMessage[]) => {
  if (!debateId || !isRealDebateId(debateId) || messages.length === 0) return;
  try {
    const res = await fetch(`/api/debate/${debateId}/coach-transcript`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: messages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
      }),
    });
    if (!res.ok) {
      console.error('保存策略教练对话失败:', res.status, await res.text());
    }
  } catch (err) {
    console.error('保存策略教练对话失败:', err);
  }
};

// 金融科普对话消息
interface KnowledgeMessage {
  role: 'agent' | 'user';
  content: string;
  timestamp: Date;
  related_terms?: string[];
}

function findKnowledgeSource(node: Node | null): string {
  let el: Element | null = node instanceof Element ? node : node?.parentElement ?? null;
  while (el) {
    const source = el.getAttribute('data-knowledge-source');
    if (source === 'bull') return '多头观点';
    if (source === 'bear') return '空头观点';
    if (source === 'judge') return '裁判裁决';
    if (el.id === 'debate-content-area') break;
    el = el.parentElement;
  }
  return '';
}

export default function BrainstormPage() {
  const router = useRouter();
  const { toast } = useToast();
  const knowledgeInputRef = useRef<HTMLInputElement>(null);
  const knowledgeAnchorRef = useRef('');
  
  // 状态
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Stock[]>([]);
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);
  const [debateHistory, setDebateHistory] = useState<DebateHistoryItem[]>([]);
  const [autoLoadedTicker, setAutoLoadedTicker] = useState('');
  const [savedDebateKey, setSavedDebateKey] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [searchAttempted, setSearchAttempted] = useState(false);
  // 策略教练
  const [showCoachPanel, setShowCoachPanel] = useState(false); // 辩论完成后才展开
  const [coachMessages, setCoachMessages] = useState<CoachMessage[]>([]);
  const [coachInput, setCoachInput] = useState('');
  const [isCoachLoading, setIsCoachLoading] = useState(false);
  const [coachState, setCoachState] = useState<CoachState>('opening');
  const [coachSuggestedQuestions, setCoachSuggestedQuestions] = useState<string[]>([]);
  const [canSaveCoachStrategy, setCanSaveCoachStrategy] = useState(false);
  const [savedCoachDossierId, setSavedCoachDossierId] = useState<number | null>(null);
  const [showStrategyCardPreview, setShowStrategyCardPreview] = useState(false);

  // 金融科普Agent
  const [showKnowledgePanel, setShowKnowledgePanel] = useState(false);
  const [selectedKnowledgeText, setSelectedKnowledgeText] = useState('');
  const [selectedContext, setSelectedContext] = useState(''); // 来源：多头/空头/裁判
  const [knowledgeMessages, setKnowledgeMessages] = useState<KnowledgeMessage[]>([]);
  const [isKnowledgeLoading, setIsKnowledgeLoading] = useState(false);
  const [showKnowledgeButton, setShowKnowledgeButton] = useState(false);
  const [knowledgeButtonPos, setKnowledgeButtonPos] = useState({ x: 0, y: 0 });
  
  // 辩论结果（用于策略教练）
  const [debateResult, setDebateResult] = useState<JudgeVerdict | null>(null);

  const refreshDebateHistory = async () => {
    const localHistory = readLocalDebateHistory();
    try {
      const backendHistory = await fetchDebateHistory(6);
      const merged = mergeDebateHistory(backendHistory, localHistory).slice(0, 6);
      setDebateHistory(merged);
      writeLocalDebateHistory(merged);
    } catch {
      setDebateHistory(localHistory.slice(0, 6));
    }
  };

  // 辩论 SSE 流（状态 + 启停）
  const {
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
  } = useDebateStream({
    onDebateStart: () => {
      setCoachMessages([]);
      setCoachSuggestedQuestions([]);
      setCanSaveCoachStrategy(false);
      setCoachState('opening');
      setShowCoachPanel(false);
    },
    onComplete: () => {
      refreshDebateHistory();
    },
    toast,
  });

  useEffect(() => {
    if (!showCoachPanel && !showKnowledgePanel) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setShowCoachPanel(false);
        setShowKnowledgePanel(false);
      }
    };
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [showCoachPanel, showKnowledgePanel]);

  useEffect(() => {
    if (judgeVerdict && !isStreaming && selectedStock && currentDebateId && coachMessages.length === 0) {
      initCoachAfterDebate(judgeVerdict);
    }
  }, [judgeVerdict, isStreaming, selectedStock, currentDebateId, coachMessages.length, rounds]);

  // 最近辩论：优先后端记录，本地仅作离线兜底
  useEffect(() => {
    refreshDebateHistory();
  }, []);

  useEffect(() => {
    if (!judgeVerdict || isStreaming || !selectedStock || !currentDebateId) return;

    const debateKey = `${currentDebateId}-${selectedStock.ts_code}`;
    if (debateKey === savedDebateKey) return;

    const item: DebateHistoryItem = {
      id: currentDebateId,
      ticker: selectedStock.ts_code,
      ticker_name: selectedStock.name,
      coverage,
      rating: judgeVerdict.rating,
      summary: judgeVerdict.summary,
      rounds_count: rounds.length,
      created_at: new Date().toISOString(),
    };

    setDebateHistory(prev => {
      const merged = mergeDebateHistory([item], prev).slice(0, 6);
      writeLocalDebateHistory(merged);
      return merged;
    });
    setSavedDebateKey(debateKey);
  }, [judgeVerdict, isStreaming, selectedStock, currentDebateId, coverage, rounds.length, savedDebateKey]);

  useEffect(() => {
    if (autoLoadedTicker) return;
    const params = new URLSearchParams(window.location.search);
    const ticker = params.get('ticker');
    if (!ticker) return;

    const stock: Stock = {
      ts_code: ticker,
      name: params.get('name') || ticker,
      code: ticker.split('.')[0] || ticker,
      price: 0,
      industry: '',
    };
    setAutoLoadedTicker(ticker);
    handleSelectStock(stock);
  }, [autoLoadedTicker]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    
    setIsSearching(true);
    setSearchError('');
    setSearchAttempted(true);
    try {
      const res = await fetch(`/api/stock/search?q=${encodeURIComponent(searchQuery)}`);
      if (!res.ok) throw new Error('搜索失败');
      const data = await res.json();
      setSearchResults(data);
    } catch (err) {
      console.error('搜索失败:', err);
      setSearchResults([]);
      setSearchError('搜索失败，请检查网络后重试');
      toast('股票搜索失败，请稍后重试', 'error');
    } finally {
      setIsSearching(false);
    }
  };
  
  // 选择股票
  const handleSelectStock = (stock: Stock) => {
    setSelectedStock(stock);
    setSearchQuery('');
    setSearchResults([]);
    setSearchError('');
    setSearchAttempted(false);
  };

  const handleOpenHistory = async (item: DebateHistoryItem) => {
    const stock: Stock = {
      ts_code: item.ticker,
      name: item.ticker_name || item.ticker,
      code: item.ticker.split('.')[0] || item.ticker,
      price: 0,
      industry: '',
    };
    setSelectedStock(stock);
    setSearchQuery('');
    setSearchResults([]);
    setCoverage(item.coverage || 0);
    setStatusMessage(item.summary ? `最近裁决：${item.rating || '已完成'} · ${item.summary}` : '已载入历史股票，可直接发起新辩论');
    setCurrentDebateId(null);
    setRounds([]);
    setJudgeVerdict(null);
    setDataCardFields({});
    setCoachMessages([]);
    setCoachSuggestedQuestions([]);
    setCanSaveCoachStrategy(false);
    setDebateResult(null);
    setCoachState('opening');

    try {
      const res = await fetch(`/api/debate/history/${item.id}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const detail: DebateHistoryDetail = await res.json();
      const detailRounds = (detail.rounds || []).map((round) => ({
        round: round.round,
        bull_content: round.bull_content || round.bull || '',
        bear_content: round.bear_content || round.bear || '',
      }));
      setCurrentDebateId(detail.id);
      setRounds(detailRounds);
      setCoverage(detail.coverage || detail.data_card?.coverage || 0);
      setDataCardFields(detail.data_card?.fields || {});
      setJudgeVerdict(detail.judge_verdict || null);
      setDebateResult(detail.judge_verdict || null);
      const restoredCoachMessages = (detail.coach_messages || []).map((message) => ({
        role: message.role,
        content: message.content,
        timestamp: message.timestamp ? new Date(message.timestamp) : new Date(),
      }));
      setCoachMessages(restoredCoachMessages);
      if (restoredCoachMessages.length > 0) {
        setShowCoachPanel(true);
        setCoachState('chatting');
      }
      setStatusMessage(
        restoredCoachMessages.length > 0
          ? `已载入历史辩论：${detailRounds.length} 轮 + ${restoredCoachMessages.length} 条教练对话`
          : `已载入历史辩论：${detailRounds.length} 轮，多空记录已恢复`,
      );
    } catch (err) {
      console.error('加载辩论历史详情失败:', err);
      setStatusMessage(item.summary ? `最近裁决：${item.rating || '已完成'} · ${item.summary}` : '历史详情加载失败，仅载入股票信息');
    }
  };
  
  const buildCoachDebateResult = () => {
    if (rounds.length === 0) return null;
    return {
      rounds,
      judge: judgeVerdict,
      data_card: Object.keys(dataCardFields).length > 0
        ? { coverage, fields: dataCardFields }
        : null,
    };
  };

  const buildCoachRequestBody = (
    messages: CoachMessage[],
    extra: Record<string, unknown> = {}
  ) => ({
    ticker: selectedStock?.ts_code || '',
    ticker_name: selectedStock?.name || '',
    debate_result: buildCoachDebateResult(),
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
    state: coachState,
    ...extra,
  });

  const applyCoachDoneMeta = (event: CoachStreamEvent) => {
    if (event.state) setCoachState(event.state as CoachState);
    setCoachSuggestedQuestions(event.suggested_questions || []);
    setCanSaveCoachStrategy(Boolean(event.can_save_strategy));
    if (event.strategy_saved && event.dossier_id) {
      setSavedCoachDossierId(event.dossier_id);
    }
    if (event.state === 'reviewing') setShowStrategyCardPreview(true);
  };

  const consumeCoachStream = async (
    requestBody: Record<string, unknown>,
    baseMessages: CoachMessage[]
  ) => {
    const messagesWithPlaceholder: CoachMessage[] = [
      ...baseMessages,
      { role: 'coach', content: '', timestamp: new Date() },
    ];
    setCoachMessages(messagesWithPlaceholder);
    setIsCoachLoading(true);

    try {
      await streamCoachChat(requestBody, (event) => {
        if (event.type === 'token') {
          setCoachMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last?.role === 'coach') {
              updated[updated.length - 1] = {
                ...last,
                content: last.content + (event.delta || ''),
              };
            }
            return updated;
          });
          return;
        }

        if (event.type === 'done') {
          setCoachMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last?.role === 'coach') {
              updated[updated.length - 1] = {
                ...last,
                content: event.reply || last.content,
              };
            }
            saveCoachTranscript(currentDebateId, updated);
            return updated;
          });
          applyCoachDoneMeta(event);
          return;
        }

        if (event.type === 'error') {
          throw new Error(event.message || '教练流式输出失败');
        }
      });
    } catch (err) {
      console.error('策略教练流式对话失败:', err);
      toast('策略教练回复失败，请重试', 'error');
      setCoachMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.role === 'coach' && !last.content) {
          updated[updated.length - 1] = {
            ...last,
            content: '教练回复失败，请稍后重试。',
          };
        }
        return updated;
      });
    } finally {
      setIsCoachLoading(false);
    }
  };

  // 策略教练对话
  const handleQuickReply = (text: string) => {
    if (!text.trim() || !selectedStock) return;

    if (text === '回到卷宗查看策略' && savedCoachDossierId) {
      router.push(`/dossier/${savedCoachDossierId}`);
      return;
    }

    const userMessage: CoachMessage = {
      role: 'user',
      content: text,
      timestamp: new Date(),
    };
    const newMessages = [...coachMessages, userMessage];
    setCoachInput('');
    void consumeCoachStream(buildCoachRequestBody(newMessages), newMessages);
  };

  const handleSendCoachMessage = async () => {
    if (!coachInput.trim() || !selectedStock) return;

    const userMessage: CoachMessage = {
      role: 'user',
      content: coachInput,
      timestamp: new Date(),
    };
    const newMessages = [...coachMessages, userMessage];
    setCoachInput('');
    await consumeCoachStream(buildCoachRequestBody(newMessages), newMessages);
  };

  // 初始化策略教练（辩论完成后，流式获取开场白）
  const initCoachAfterDebate = async (verdict: JudgeVerdict | null) => {
    if (verdict && selectedStock) {
      setDebateResult(verdict);
      setShowCoachPanel(true);
      try {
        await consumeCoachStream(
          buildCoachRequestBody([], {
            state: 'opening',
            debate_result: {
              rounds,
              judge: verdict,
              data_card: Object.keys(dataCardFields).length > 0
                ? { coverage, fields: dataCardFields }
                : null,
            },
            messages: [],
          }),
          []
        );
      } catch (err) {
        console.error('初始化教练失败:', err);
        const fallbackMessage: CoachMessage = {
          role: 'coach',
          content: '欢迎！我是策略教练，将帮你基于刚才的辩论，制定可执行的策略卡片。',
          timestamp: new Date(),
        };
        setCoachMessages([fallbackMessage]);
        setCoachSuggestedQuestions([
          '这个策略最大的风险是什么？',
          '现在价格是否值得入场？',
          '帮我把入场和退出条件写具体',
        ]);
        setCanSaveCoachStrategy(false);
        saveCoachTranscript(currentDebateId, [fallbackMessage]);
      } finally {
        setIsCoachLoading(false);
      }
    }
  };
  
  // 金融科普Agent - 处理文本选择
  // 金融科普 - document级mouseup监听
  useEffect(() => {
    const handleMouseUp = (e: MouseEvent) => {
      // 延迟获取selection，确保浏览器完成选区更新
      setTimeout(() => {
        const selection = window.getSelection();
        if (selection && selection.toString().trim().length > 0) {
          const selectedText = selection.toString().trim();
          const anchorNode = selection.anchorNode;
          if (anchorNode) {
            const debateArea = document.getElementById('debate-content-area');
            if (debateArea && debateArea.contains(anchorNode)) {
              const source = findKnowledgeSource(anchorNode);
              setSelectedContext(source);
              if (knowledgeAnchorRef.current && knowledgeAnchorRef.current !== selectedText) {
                setKnowledgeMessages([]);
              }
              knowledgeAnchorRef.current = selectedText;
              setSelectedKnowledgeText(selectedText);
              setShowKnowledgeButton(true);
              setKnowledgeButtonPos({ x: e.clientX, y: e.clientY });
              return;
            }
          }
        }
        setShowKnowledgeButton(false);
      }, 10);
    };

    document.addEventListener('mouseup', handleMouseUp);
    return () => document.removeEventListener('mouseup', handleMouseUp);
  }, []);
  
  // 金融科普Agent - 发送提问
  const handleKnowledgeAsk = async (customText?: string) => {
    const anchorText = customText || selectedKnowledgeText;
    if (!anchorText.trim()) return;

    if (knowledgeAnchorRef.current !== anchorText) {
      setKnowledgeMessages([]);
      knowledgeAnchorRef.current = anchorText;
    }
    
    setShowKnowledgeButton(false);
    setShowKnowledgePanel(true);
    setIsKnowledgeLoading(true);
    
    const userMessage: KnowledgeMessage = {
      role: 'user',
      content: anchorText,
      timestamp: new Date()
    };
    const historyForApi: ApiKnowledgeMessage[] = knowledgeMessages.map((m) => ({
      role: m.role,
      content: m.content,
    }));
    setKnowledgeMessages((prev) => [...prev, userMessage]);
    
    try {
      const data = await askKnowledge({
        selected_text: anchorText,
        context: selectedContext,
        ticker: selectedStock?.ts_code || '',
        ticker_name: selectedStock?.name || '',
        question: `请解释「${anchorText}」的含义和投资意义。`,
        history: historyForApi,
      });
      
      const agentMessage: KnowledgeMessage = {
        role: 'agent',
        content: data.explanation,
        timestamp: new Date(),
        related_terms: data.related_terms,
      };
      setKnowledgeMessages((prev) => [...prev, agentMessage]);
    } catch (err) {
      console.error('金融科普提问失败:', err);
      toast(err instanceof Error ? err.message : '金融科普请求失败', 'error');
    } finally {
      setIsKnowledgeLoading(false);
    }
  };
  
  // 金融科普Agent - 继续对话
  const handleKnowledgeContinue = async (userInput: string) => {
    if (!userInput.trim()) return;

    const anchorText = knowledgeAnchorRef.current || selectedKnowledgeText;
    if (!anchorText.trim()) return;
    
    setIsKnowledgeLoading(true);
    
    const userMessage: KnowledgeMessage = {
      role: 'user',
      content: userInput,
      timestamp: new Date()
    };
    const historyForApi: ApiKnowledgeMessage[] = [
      ...knowledgeMessages.map((m) => ({ role: m.role, content: m.content })),
      { role: 'user', content: userInput },
    ];
    setKnowledgeMessages((prev) => [...prev, userMessage]);
    
    try {
      const data = await askKnowledge({
        selected_text: anchorText,
        context: selectedContext,
        ticker: selectedStock?.ts_code || '',
        ticker_name: selectedStock?.name || '',
        question: userInput,
        history: historyForApi.slice(0, -1),
      });
      
      const agentMessage: KnowledgeMessage = {
        role: 'agent',
        content: data.explanation,
        timestamp: new Date(),
        related_terms: data.related_terms,
      };
      setKnowledgeMessages((prev) => [...prev, agentMessage]);
    } catch (err) {
      console.error('金融科普对话失败:', err);
      toast(err instanceof Error ? err.message : '金融科普请求失败', 'error');
    } finally {
      setIsKnowledgeLoading(false);
    }
  };
  
  // 开始辩论（流式输出）
  const handleStartDebate = () => {
    void startDebate(selectedStock);
  };
  
  const handleStopDebate = () => {
    stopDebate();
  };
  
  // 创建卷宗
  const handleCreateDossier = async () => {
    if (!selectedStock) return;
    
    try {
      const res = await fetch('/api/dossier/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stock_code: selectedStock.ts_code }),
      });
      const data = await res.json();
      router.push(`/dossier/${data.dossier_id}`);
    } catch (err) {
      console.error('创建卷宗失败:', err);
      toast('创建卷宗失败', 'error');
    }
  };
  
  return (
    <div className="min-h-screen bg-[var(--jh-bg)]">
      <div className="container mx-auto px-4 py-8">
        <div className="flex gap-6 max-w-[1400px] mx-auto">
          
          {/* 主内容区域 */}
          <div className="flex-1 min-w-0">
          
          {/* 标题 */}
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-bold mb-2 text-[var(--jh-text)]">
              <Sparkles className="inline-block mr-2 text-[var(--jh-warm)]" />
              投资策略头脑风暴室
            </h1>
            <p className="text-[var(--jh-muted)]">
              Step 1 选股 → Step 2 多空辩论 → Step 3 策略教练
            </p>
          </div>
          
          {/* 步骤1: 股票选择 */}
          {debateHistory.length > 0 && (
            <Card className="mb-6 bg-[var(--jh-surface)] border-[var(--jh-line)]">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2 text-[var(--jh-text)]">
                  <Clock className="w-5 h-5 text-[var(--jh-accent)]" />
                  最近辩论
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {debateHistory.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleOpenHistory(item)}
                      className="text-left p-3 rounded-lg border border-[var(--jh-line)] hover:border-[var(--jh-accent)] hover:bg-[var(--jh-bg-2)] transition-all"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="font-medium text-[var(--jh-text)]">
                            {item.ticker_name || item.ticker}
                            <span className="ml-2 text-xs font-mono text-[var(--jh-muted)]">{item.ticker}</span>
                          </div>
                          <div className="mt-1 text-xs text-[var(--jh-muted)] line-clamp-1">
                            {item.summary || `${item.rounds_count || 0} 轮辩论 · 数据覆盖率 ${item.coverage || 0}%`}
                          </div>
                        </div>
                        {item.rating && (
                          <Badge className="bg-[var(--jh-warm)] text-[var(--jh-bg)] whitespace-nowrap">{item.rating}</Badge>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <Card className="mb-6 bg-[var(--jh-surface)] border-[var(--jh-line)]">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2 text-[var(--jh-text)]">
                <Search className="w-5 h-5 text-[var(--jh-accent)]" />
                Step 1: 选择目标股票
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-4">
                <div className="relative flex-1">
                  <Input
                    placeholder="输入股票代码或名称（如 600519 或 茅台）"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    className="pr-10"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute right-0 top-0"
                    onClick={handleSearch}
                    disabled={isSearching}
                  >
                    {isSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  </Button>
                </div>
              </div>
              
              {/* 搜索结果 */}
              {searchAttempted && !isSearching && searchResults.length === 0 && !searchError && (
                <div className="mt-4 p-4 text-center text-sm text-[var(--jh-muted)] border border-[var(--jh-line)] rounded-lg">
                  未找到匹配股票，请尝试代码或完整名称
                </div>
              )}
              {searchError && (
                <div className="mt-4 p-4 text-center text-sm text-[var(--jh-danger)] border border-[var(--jh-danger)]/30 rounded-lg bg-[rgba(255,122,122,0.08)]">
                  {searchError}
                </div>
              )}
              
              {searchResults.length > 0 && (
                <div className="mt-4 border border-[var(--jh-line)] rounded-lg divide-y divide-[var(--jh-line)]">
                  {searchResults.map((stock) => (
                    <button
                      key={stock.ts_code}
                      type="button"
                      className="w-full p-3 hover:bg-[var(--jh-bg-2)] cursor-pointer flex items-center justify-between text-[var(--jh-text)] text-left"
                      onClick={() => handleSelectStock(stock)}
                    >
                      <div>
                        <span className="font-medium">{stock.name}</span>
                        <span className="ml-2 text-[var(--jh-muted)]">{stock.ts_code}</span>
                        {stock.industry && (
                          <Badge variant="outline" className="ml-2 border-[var(--jh-line)] text-[var(--jh-muted)]">{stock.industry}</Badge>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}
              
              {/* 已选择 */}
              {selectedStock && (
                <div className="mt-4 p-4 bg-[var(--jh-bg-2)] border border-[var(--jh-accent)] rounded-lg flex items-center justify-between">
                  <div>
                    <span className="font-bold text-lg text-[var(--jh-text)]">{selectedStock.name}</span>
                    <span className="ml-2 text-[var(--jh-muted)]">{selectedStock.ts_code}</span>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedStock(null)} className="text-[var(--jh-muted)]">
                    更换
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
          
          {/* 步骤2: 开始辩论 */}
          {selectedStock && (
            <Card className="mb-6 bg-[var(--jh-surface)] border-[var(--jh-line)]">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2 text-[var(--jh-text)]">
                  <Scale className="w-5 h-5 text-[var(--jh-accent)]" />
                  Step 2: 启动AI多空辩论
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    onClick={handleStartDebate}
                    disabled={isStreaming}
                    className="bg-[var(--jh-accent)] text-[var(--jh-bg)] hover:bg-[var(--jh-accent-2)]"
                  >
                    {isStreaming ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                        辩论进行中...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4 mr-2" />
                        开始头脑风暴
                      </>
                    )}
                  </Button>
                  
                  {isStreaming && (
                    <Button variant="outline" onClick={handleStopDebate}>
                      停止
                    </Button>
                  )}
                </div>
                
                {/* 状态消息 */}
                {statusMessage && (
                  <div className="mt-4 p-3 bg-[var(--jh-bg-2)] rounded-lg text-center text-[var(--jh-muted)]">
                    {statusMessage}
                    {coverage > 0 && (
                      <Badge className="ml-2 bg-[var(--jh-surface)] text-[var(--jh-text)]">
                        数据覆盖率: {coverage}%
                      </Badge>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
          
          {/* 数据卡展示 */}
          {Object.keys(dataCardFields).length > 0 && (
            <Card className="mb-6 bg-[var(--jh-surface)] border-[var(--jh-line)]">
              <CardHeader>
                <CardTitle className="text-lg text-[var(--jh-text)] flex items-center gap-2">
                  <Search className="w-5 h-5 text-[var(--jh-accent)]" />
                  数据卡
                  <Badge className="bg-[var(--jh-accent)] text-[var(--jh-bg)]">覆盖率 {coverage}%</Badge>
                </CardTitle>
                <p className="text-xs text-[var(--jh-muted)] mt-1">
                  <span className="text-[var(--jh-accent)] font-medium">A级</span> = 交叉验证通过
                  <span className="mx-2">·</span>
                  <span className="text-[var(--jh-warm)] font-medium">B级</span> = 单源直采
                  <span className="mx-2">·</span>
                  <span className="text-red-400 font-medium">C级</span> = 多源偏差超限
                </p>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                  {Object.entries(dataCardFields).map(([key, info]) => {
                    const val = info.value;
                    const displayVal = val === null || val === undefined ? '—' : String(val);
                    const gradeColor = info.grade === 'A'
                      ? 'text-[var(--jh-accent)]'
                      : info.grade === 'B'
                        ? 'text-[var(--jh-warm)]'
                        : info.grade === 'C'
                          ? 'text-red-400'
                          : 'text-[var(--jh-muted)]';
                    const timeNote = info.period_label && info.as_of
                      ? `${info.period_label} · ${info.as_of}`
                      : info.as_of || '';
                    const cardBorder = info.grade === 'C' ? 'border-red-400/40' : 'border-[var(--jh-line)]';
                    return (
                      <div key={key} className={`p-2 bg-[var(--jh-bg-2)] rounded-lg border ${cardBorder}`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-[var(--jh-muted)] truncate" title={key}>{key}</span>
                          <span className={`text-[10px] font-medium ${gradeColor}`}>{info.grade}</span>
                        </div>
                        <div className="text-sm font-semibold text-[var(--jh-text)] truncate" title={displayVal}>{displayVal}</div>
                        {timeNote && (
                          <div className="text-[10px] text-[var(--jh-muted)] truncate mt-0.5" title={timeNote}>{timeNote}</div>
                        )}
                        {info.period_warning && (
                          <div className="text-[10px] text-amber-400 truncate mt-0.5" title={info.period_warning}>⚠ {info.period_warning}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}
          
          {/* Step 3: 策略教练引导 */}
          {judgeVerdict && !isStreaming && (
            <Card className="mb-6 bg-[var(--jh-surface)] border-[var(--jh-accent)] border-l-4">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2 text-[var(--jh-text)]">
                  <MessageSquare className="w-5 h-5 text-[var(--jh-accent)]" />
                  Step 3: 策略教练
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-[var(--jh-muted)] mb-4">
                  辩论已完成（评级 {judgeVerdict.rating}）。策略教练将帮你把多空观点转化为可执行的策略卡片。
                </p>
                <div className="flex flex-wrap gap-3">
                  <Button
                    onClick={() => setShowCoachPanel(true)}
                    className="bg-[var(--jh-accent)] text-[var(--jh-bg)] hover:bg-[var(--jh-accent-2)]"
                  >
                    <MessageSquare className="w-4 h-4 mr-2" />
                    打开策略教练
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleCreateDossier}
                    className="border-[var(--jh-line)]"
                  >
                    先创建卷宗档案
                  </Button>
                </div>
                <p className="text-xs text-[var(--jh-text-muted)] mt-3">
                  「保存当前策略」由教练写入卷宗；「创建卷宗档案」仅建立股票档案，不含策略内容。
                </p>
              </CardContent>
            </Card>
          )}
          
          {/* 辩论结果展示 - 三栏并排布局 */}
          <DebatePanel
            rounds={rounds}
            judgeVerdict={judgeVerdict}
            isStreaming={isStreaming}
            streamingSide={streamingSide}
            streamingRound={streamingRound}
            onOpenCoach={() => setShowCoachPanel(true)}
          />
          
          {/* 金融科普悬浮按钮 */}
          {showKnowledgeButton && selectedKnowledgeText && (
            <button
              type="button"
              onClick={() => {
                setShowKnowledgePanel(true);
                setShowKnowledgeButton(false);
              }}
              className="fixed z-50 bg-[var(--jh-accent)] text-[var(--jh-bg)] px-3 py-1.5 rounded-lg shadow-lg text-sm font-medium hover:bg-[var(--jh-accent-2)] transition-colors max-w-[calc(100vw-2rem)]"
              style={{ left: `clamp(1rem, ${knowledgeButtonPos.x + 10}px, calc(100vw - 8rem))`, top: `max(0.5rem, ${knowledgeButtonPos.y - 40}px)` }}
            >
              金融科普
            </button>
          )}
          
          {/* 主内容区域结束 */}
          </div>
          
        </div>
        
        {/* 策略教练聊天对话框 */}
        {showCoachPanel && (
          <CoachPanel
            coachMessages={coachMessages}
            coachInput={coachInput}
            onCoachInputChange={setCoachInput}
            isCoachLoading={isCoachLoading}
            coachState={coachState}
            coachSuggestedQuestions={coachSuggestedQuestions}
            canSaveCoachStrategy={canSaveCoachStrategy}
            savedCoachDossierId={savedCoachDossierId}
            debateResult={debateResult}
            onClose={() => setShowCoachPanel(false)}
            onSendMessage={handleSendCoachMessage}
            onQuickReply={handleQuickReply}
            onOpenDossier={(dossierId) => router.push(`/dossier/${dossierId}`)}
          />
        )}

      {/* 金融科普悬浮面板 */}
      {showKnowledgePanel && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          onClick={() => setShowKnowledgePanel(false)}
          role="dialog"
          aria-modal="true"
          aria-label="金融科普"
        >
          <div
            className="w-full max-w-[480px] max-h-[min(600px,85vh)] bg-[var(--jh-surface)] border border-[var(--jh-line)] rounded-xl shadow-2xl flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 面板头部 */}
            <div className="flex items-center justify-between p-4 border-b border-[var(--jh-line)]">
              <div className="flex items-center gap-2">
                <BookOpen className="w-5 h-5 text-[var(--jh-accent)]" />
                <h3 className="font-semibold text-[var(--jh-text)]">金融科普</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowKnowledgePanel(false)}
                className="text-[var(--jh-muted)] hover:text-[var(--jh-text)] transition-colors"
                aria-label="关闭金融科普"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 选中文本展示 */}
            {selectedKnowledgeText && (
              <div className="mx-4 mt-3 p-3 bg-[rgba(99,230,208,0.08)] border border-[var(--jh-accent)]/20 rounded-lg">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="text-xs text-[var(--jh-accent)]">关注内容</div>
                  {selectedContext && (
                    <div className="text-[10px] text-[var(--jh-muted)]">{selectedContext}</div>
                  )}
                </div>
                <div className="text-sm text-[var(--jh-text)] line-clamp-3">&ldquo;{selectedKnowledgeText}&rdquo;</div>
              </div>
            )}

            {/* 对话内容 */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {knowledgeMessages.map((msg, idx) => (
                <div key={idx} className={`p-3 rounded-lg ${
                  msg.role === 'user'
                    ? 'bg-[rgba(99,230,208,0.1)] border border-[var(--jh-accent)]/30'
                    : 'bg-[var(--jh-bg-2)] border border-[var(--jh-line)]'
                }`}>
                  <div className="text-xs text-[var(--jh-muted)] mb-1">
                    {msg.role === 'user' ? '提问' : '金融科普Agent'}
                  </div>
                  <div className="text-sm text-[var(--jh-text)] knowledge-content">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                  {msg.role === 'agent' && msg.related_terms && msg.related_terms.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {msg.related_terms.map((term) => (
                        <span
                          key={term}
                          className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(255,255,255,0.05)] text-[var(--jh-muted)] border border-[var(--jh-line)]"
                        >
                          {term}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {isKnowledgeLoading && (
                <div className="flex items-center gap-2 p-3 text-[var(--jh-muted)] text-sm">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  正在分析...
                </div>
              )}
              {knowledgeMessages.length === 0 && !isKnowledgeLoading && (
                <div className="text-center text-[var(--jh-muted)] text-sm py-8">
                  点击下方按钮，向AI提问选中文本的含义
                </div>
              )}
            </div>

            {/* 追问输入 */}
            <div className="p-3 border-t border-[var(--jh-line)]">
              <div className="flex gap-2">
                <input
                  ref={knowledgeInputRef}
                  className="flex-1 bg-[var(--jh-bg-2)] border border-[var(--jh-line)] rounded-lg px-3 py-2 text-sm text-[var(--jh-text)] placeholder:text-[var(--jh-muted)] focus:outline-none focus:border-[var(--jh-accent)]"
                  placeholder="追问更多..."
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.target as HTMLInputElement).value.trim()) {
                      const val = (e.target as HTMLInputElement).value.trim();
                      (e.target as HTMLInputElement).value = '';
                      if (knowledgeMessages.length === 0) {
                        setSelectedKnowledgeText(val);
                        knowledgeAnchorRef.current = val;
                        void handleKnowledgeAsk(val);
                      } else {
                        void handleKnowledgeContinue(val);
                      }
                    }
                  }}
                />
                <Button
                  size="sm"
                  onClick={() => {
                    const val = knowledgeInputRef.current?.value.trim();
                    if (!val) {
                      if (selectedKnowledgeText.trim()) void handleKnowledgeAsk();
                      return;
                    }
                    knowledgeInputRef.current!.value = '';
                    if (knowledgeMessages.length === 0) {
                      setSelectedKnowledgeText(val);
                      knowledgeAnchorRef.current = val;
                      void handleKnowledgeAsk(val);
                    } else {
                      void handleKnowledgeContinue(val);
                    }
                  }}
                  disabled={isKnowledgeLoading}
                  className="bg-[var(--jh-accent)] text-[var(--jh-bg)]"
                >
                  {knowledgeMessages.length === 0 ? '提问' : '追问'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
    </div>
  );
}
