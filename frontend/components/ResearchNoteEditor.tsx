"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bold,
  Italic,
  List,
  ListOrdered,
  Heading2,
  Eye,
  PenLine,
  Loader2,
} from "lucide-react";
import { getDossierByStock, updateResearchNote } from "@/lib/api";

const RESEARCH_NOTE_PREFIX = "jingheng_research_note:";

type SaveState = "idle" | "saving" | "saved" | "local" | "error";

const SAVE_STATE_LABEL: Record<SaveState, { text: string; className: string }> = {
  idle: { text: "待输入", className: "text-[var(--jh-text-muted)]" },
  saving: { text: "保存中…", className: "text-[var(--jh-text-secondary)]" },
  saved: { text: "已同步卷宗", className: "text-[var(--jh-accent)]" },
  local: { text: "仅本地", className: "text-[var(--jh-warning)]" },
  error: { text: "同步失败", className: "text-[var(--jh-danger)]" },
};

interface ResearchNoteEditorProps {
  stockCode: string;
  stockName: string;
  /** 若已持有卷宗数据，可跳过首次拉取 */
  initialNote?: string;
  /** sidebar=研究台右侧栏；page=卷宗页；coach=策略审查并排面板 */
  variant?: "sidebar" | "page" | "coach";
  onSaved?: (note: string) => void;
}

export default function ResearchNoteEditor({
  stockCode,
  stockName,
  initialNote,
  variant = "sidebar",
  onSaved,
}: ResearchNoteEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;
  const loadedStockRef = useRef<string | null>(null);
  const [researchNote, setResearchNote] = useState(initialNote ?? "");
  const [noteSaveState, setNoteSaveState] = useState<SaveState>("idle");
  const [showPreview, setShowPreview] = useState(false);

  useEffect(() => {
    if (!stockCode || typeof window === "undefined") {
      setResearchNote("");
      setNoteSaveState("idle");
      loadedStockRef.current = null;
      return;
    }

    if (loadedStockRef.current === stockCode) return;
    loadedStockRef.current = stockCode;

    let cancelled = false;
    const localNote =
      window.localStorage.getItem(`${RESEARCH_NOTE_PREFIX}${stockCode}`) || "";

    if (initialNote !== undefined) {
      const merged = initialNote || localNote;
      setResearchNote(merged);
      setNoteSaveState(merged ? (initialNote ? "saved" : "local") : "idle");
      if (merged) {
        window.localStorage.setItem(`${RESEARCH_NOTE_PREFIX}${stockCode}`, merged);
      }
      return;
    }

    setResearchNote(localNote);
    setNoteSaveState(localNote ? "local" : "idle");

    getDossierByStock(stockCode)
      .then((dossier) => {
        if (cancelled) return;
        const merged = dossier.research_note || localNote;
        setResearchNote(merged);
        setNoteSaveState(dossier.research_note ? "saved" : localNote ? "local" : "idle");
        if (merged) {
          window.localStorage.setItem(`${RESEARCH_NOTE_PREFIX}${stockCode}`, merged);
        }
      })
      .catch(() => {
        if (!cancelled) setNoteSaveState(localNote ? "local" : "idle");
      });

    return () => {
      cancelled = true;
    };
  }, [stockCode, initialNote]);

  useEffect(() => {
    if (!stockCode || typeof window === "undefined") return;

    window.localStorage.setItem(`${RESEARCH_NOTE_PREFIX}${stockCode}`, researchNote);

    if (!researchNote.trim()) {
      setNoteSaveState("idle");
      return;
    }

    setNoteSaveState("saving");
    const timer = window.setTimeout(() => {
      updateResearchNote(stockCode, stockName, researchNote)
        .then((dossier) => {
          const saved = dossier.research_note || researchNote;
          setResearchNote(saved);
          setNoteSaveState("saved");
          onSavedRef.current?.(saved);
        })
        .catch(() => {
          setNoteSaveState("error");
        });
    }, 700);

    return () => window.clearTimeout(timer);
  }, [researchNote, stockCode, stockName]);

  const applyFormat = (before: string, after = before, placeholder = "文本") => {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const selected = researchNote.slice(start, end) || placeholder;
    const next = `${researchNote.slice(0, start)}${before}${selected}${after}${researchNote.slice(end)}`;
    setResearchNote(next);
    window.setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + before.length, start + before.length + selected.length);
    }, 0);
  };

  const insertLinePrefix = (prefix: string) => {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const lineStart = researchNote.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    const next = `${researchNote.slice(0, lineStart)}${prefix}${researchNote.slice(lineStart)}`;
    setResearchNote(next);
    window.setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + prefix.length, start + prefix.length);
    }, 0);
  };

  const toolbarBtn =
    "inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-[var(--jh-text-muted)] hover:border-[var(--jh-line)] hover:bg-[var(--jh-bg-2)] hover:text-[var(--jh-text)] transition-colors";

  const textareaHeight =
    variant === "page"
      ? "min-h-[480px]"
      : variant === "coach"
        ? "flex-1 min-h-[160px] h-full"
        : "h-[360px] xl:h-[420px]";
  const saveLabel = SAVE_STATE_LABEL[noteSaveState];
  const rootClass =
    variant === "page"
      ? "glass-card overflow-hidden"
      : variant === "coach"
        ? "flex h-full min-h-0 flex-col overflow-hidden"
        : "";

  return (
    <div className={rootClass}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--jh-line)] px-3 py-2">
        <div className="flex flex-wrap items-center gap-1">
          <button
            type="button"
            className={toolbarBtn}
            title="加粗"
            aria-label="加粗"
            onClick={() => applyFormat("**", "**")}
          >
            <Bold className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className={toolbarBtn}
            title="斜体"
            aria-label="斜体"
            onClick={() => applyFormat("*", "*")}
          >
            <Italic className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className={toolbarBtn}
            title="二级标题"
            aria-label="二级标题"
            onClick={() => insertLinePrefix("## ")}
          >
            <Heading2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className={toolbarBtn}
            title="无序列表"
            aria-label="无序列表"
            onClick={() => insertLinePrefix("- ")}
          >
            <List className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className={toolbarBtn}
            title="有序列表"
            aria-label="有序列表"
            onClick={() => insertLinePrefix("1. ")}
          >
            <ListOrdered className="h-3.5 w-3.5" />
          </button>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-[var(--jh-text-muted)] hover:bg-[var(--jh-bg-2)] hover:text-[var(--jh-text)]"
          onClick={() => setShowPreview((value) => !value)}
        >
          {showPreview ? (
            <>
              <PenLine className="h-3.5 w-3.5" /> 编辑
            </>
          ) : (
            <>
              <Eye className="h-3.5 w-3.5" /> 预览
            </>
          )}
        </button>
      </div>

      <div className={variant === "coach" ? "flex min-h-0 flex-1 flex-col p-3" : "p-4"}>
        <div className={variant === "coach" ? "min-h-0 flex-1" : ""}>
        {showPreview ? (
          <div
            className={`${textareaHeight} overflow-auto rounded-md border border-[var(--jh-line)] bg-[var(--jh-bg-2)] p-3 text-sm leading-relaxed text-[var(--jh-text)] prose prose-invert prose-sm max-w-none`}
          >
            {researchNote.trim() ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{researchNote}</ReactMarkdown>
            ) : (
              <p className="text-[var(--jh-text-muted)]">暂无内容，切换回编辑模式开始记录。</p>
            )}
          </div>
        ) : (
          <textarea
            ref={textareaRef}
            value={researchNote}
            onChange={(event) => setResearchNote(event.target.value)}
            placeholder="记录投资假设、待验证事项、管理层问题、价格触发条件… 支持 **加粗**、*斜体*、列表等 Markdown 语法。"
            className={`${textareaHeight} w-full resize-none rounded-md border border-[var(--jh-line)] bg-[var(--jh-bg-2)] p-3 text-sm leading-relaxed text-[var(--jh-text)] placeholder:text-[var(--jh-text-muted)] outline-none focus:border-[var(--jh-border-strong)]`}
          />
        )}
        </div>

        <div className={`${variant === "coach" ? "mt-2 shrink-0" : "mt-3"} grid grid-cols-2 gap-2 text-xs text-[var(--jh-text-muted)]`}>
          <div className="rounded-md border border-[var(--jh-line)] p-2">
            字数 <span className="numeric text-[var(--jh-text)]">{researchNote.length}</span>
          </div>
          <div className="flex items-center gap-1.5 rounded-md border border-[var(--jh-line)] p-2">
            自动保存
            {noteSaveState === "saving" && (
              <Loader2 className="h-3 w-3 animate-spin text-[var(--jh-text-secondary)]" />
            )}
            <span className={saveLabel.className}>{saveLabel.text}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
