"use client";

import type { StrategyContent, StrategyDimension } from "@/types";

interface StrategyCardViewProps {
  content: StrategyContent;
  compact?: boolean;
}

function isCoachChitchatLine(line: string): boolean {
  const s = line.trim();
  if (!s) return false;
  if (/^\d+\.\s/.test(s)) return true;
  if (s.endsWith("？") || s.endsWith("?")) return true;
  const keywords = [
    "以上就是", "初步策略", "继续深挖", "路线图", "随时保存",
    "告诉我你想", "往哪个方向", "探讨几件事", "操作参考",
  ];
  if (keywords.some((k) => s.includes(k))) return true;
  if (s.endsWith("：") || s.endsWith(":")) {
    const colonPrefixes = ["如果", "接下来", "欢迎", "你可以", "告诉", "以上", "想"];
    if (colonPrefixes.some((p) => s.startsWith(p))) return true;
  }
  const prefixes = [
    "还有什么", "欢迎", "如果", "你可以", "需要我", "随时", "接下来",
    "以上", "希望这", "请告诉我", "想深入讨论", "可以继续追问", "告诉我",
  ];
  return prefixes.some((p) => s.startsWith(p));
}

/** 从文本中提取「## 当前策略」块 */
export function extractCurrentStrategyBlock(text: string): string {
  if (!text?.trim()) return "";
  const trimmed = text.trim();
  for (const marker of ["## 当前策略", "##当前策略"]) {
    const idx = trimmed.indexOf(marker);
    if (idx < 0) continue;
    const lines = trimmed.slice(idx).split("\n");
    const kept: string[] = [];
    for (let i = 0; i < lines.length; i++) {
      if (i > 0 && lines[i].startsWith("## ") && !lines[i].startsWith("### ")) break;
      if (i > 0 && isCoachChitchatLine(lines[i])) break;
      kept.push(lines[i]);
    }
    while (kept.length && !kept[kept.length - 1].trim()) kept.pop();
    while (kept.length && isCoachChitchatLine(kept[kept.length - 1])) {
      kept.pop();
      while (kept.length && !kept[kept.length - 1].trim()) kept.pop();
    }
    const block = kept.join("\n").trim();
    if (block) return block;
  }
  return "";
}

function legacyDimensionText(dimensions?: StrategyDimension[]): string {
  if (!dimensions?.length) return "";
  const summary = dimensions.find(
    (d) => d.dimension === "策略总结" || d.name === "策略总结"
  );
  if (!summary) return "";
  return summary.qualitative_judgment || summary.user_view || summary.description || "";
}

/** 从策略 JSON 中取出用于展示的「当前策略」正文 */
export function getStrategyDisplayText(content: StrategyContent): string {
  if (content.current_strategy?.trim()) {
    return extractCurrentStrategyBlock(content.current_strategy) || content.current_strategy.trim();
  }
  if (content.coach_conclusion?.trim()) {
    const block = extractCurrentStrategyBlock(content.coach_conclusion);
    return block || content.coach_conclusion.trim();
  }
  const legacy = legacyDimensionText(content.dimensions);
  if (legacy) {
    return extractCurrentStrategyBlock(legacy) || legacy;
  }
  return "";
}

export function StrategyCardView({ content, compact = false }: StrategyCardViewProps) {
  const text = getStrategyDisplayText(content);

  if (!text) {
    return (
      <div className="text-sm text-[var(--jh-text-muted)]">暂无策略内容</div>
    );
  }

  return (
    <div className="p-4 rounded-md border border-[var(--jh-border)] bg-[var(--jh-bg-2)]">
      <p
        className={`text-[var(--jh-text-secondary)] leading-relaxed whitespace-pre-wrap ${
          compact ? "text-xs line-clamp-6" : "text-sm"
        }`}
      >
        {text}
      </p>
    </div>
  );
}

/** 解析策略 JSON 字符串 */
export function parseStrategyContent(raw: string): StrategyContent | null {
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as StrategyContent;
  } catch {
    return null;
  }
}
