"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Search,
  Brain,
  ArrowRight,
  BarChart3,
  Target,
  ChevronRight,
} from "lucide-react";
import { WorkflowDiagram } from "@/components/WorkflowDiagram";

export default function HomePage() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  const features = [
    {
      icon: Brain,
      title: "AI 多空辩论",
      desc: "选定股票后，多头与空头 AI 基于数据卡展开辩论，强制呈现正反两面论据，帮你看清自己容易忽略的风险与机会。",
      color: "var(--jh-accent)",
      bg: "var(--jh-accent-dim)",
      href: "/brainstorm",
    },
    {
      icon: Target,
      title: "策略教练",
      desc: "教练和你一起判断基本面和估值，把结论落成策略卡片。该买还是等、盯什么、何时走，你确认，不替你做决定。",
      color: "var(--jh-info)",
      bg: "var(--jh-info-dim)",
      href: "/brainstorm",
    },
    {
      icon: BarChart3,
      title: "卷宗系统",
      desc: "为每只股票建立档案，记录策略版本和买卖记录。事后能复盘当时为什么买、策略有没有执行，持续优化你的投资策略。",
      color: "var(--jh-warning)",
      bg: "var(--jh-warning-dim)",
      href: "/dossier",
    },
  ];

  return (
    <div className="min-h-screen bg-[var(--jh-bg)]">
      {/* 顶部渐变光晕 */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-[radial-gradient(ellipse_at_center,rgba(99,230,208,0.06)_0%,transparent_70%)] pointer-events-none" />

      <div className="relative max-w-4xl mx-auto px-6 pt-20 pb-24">
        {/* Hero 区域 */}
        <div className="text-center mb-16 animate-fade-in-up">
          <h1 className="text-4xl md:text-5xl font-bold text-[var(--jh-text)] mb-4 tracking-tight">
            镜衡
          </h1>
          <p className="text-lg text-[var(--jh-text-secondary)] max-w-lg mx-auto leading-relaxed">
            照见盲点，衡定策略
          </p>
          <p className="mt-4 text-base text-[var(--jh-text-muted)] max-w-xl mx-auto leading-relaxed">
            你的AI策略思考伙伴，不替你做决策，陪你形成专属于你的个股投资策略。
          </p>

          {/* 搜索框 */}
          <form onSubmit={handleSearch} className="mt-10 max-w-md mx-auto">
            <div className="relative group">
              <div className="absolute -inset-0.5 bg-gradient-to-r from-[var(--jh-accent)]/20 to-[var(--jh-info)]/20 rounded-[var(--jh-radius-lg)] blur opacity-0 group-focus-within:opacity-100 transition-opacity duration-300" />
              <div className="relative flex flex-col sm:flex-row items-stretch sm:items-center glass-card-accent px-1 py-1 gap-1">
                <div className="flex items-center flex-1 min-w-0">
                  <Search className="w-5 h-5 text-[var(--jh-text-muted)] ml-4 flex-shrink-0" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="输入股票名称或代码，如「贵州茅台」「600519」"
                    className="flex-1 bg-transparent border-none outline-none text-[var(--jh-text)] placeholder:text-[var(--jh-text-muted)] px-3 py-3 text-sm min-w-0"
                    aria-label="搜索股票"
                  />
                </div>
                <button
                  type="submit"
                  className="jh-btn-primary flex items-center justify-center gap-1.5 px-5 py-2.5 text-sm mx-1"
                >
                  开始分析
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </form>
        </div>

        <WorkflowDiagram />

        {/* 功能卡片 */}
        <div className="mb-16 animate-fade-in-up" style={{ animationDelay: "0.2s" }}>
          <h2 className="text-center text-sm font-semibold text-[var(--jh-text-muted)] uppercase tracking-widest mb-8">
            核心能力
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {features.map((feature, i) => (
              <Link
                key={i}
                href={feature.href}
                className="glass-card p-6 group block"
              >
                <div
                  className="w-10 h-10 rounded-lg flex items-center justify-center mb-4"
                  style={{ background: feature.bg }}
                >
                  <feature.icon
                    className="w-5 h-5"
                    style={{ color: feature.color }}
                  />
                </div>
                <h3 className="text-base font-semibold text-[var(--jh-text)] mb-2 group-hover:text-[var(--jh-accent)] transition-colors">
                  {feature.title}
                </h3>
                <p className="text-sm text-[var(--jh-text-secondary)] leading-relaxed">
                  {feature.desc}
                </p>
                <div className="mt-4 flex items-center gap-1 text-xs text-[var(--jh-accent)] opacity-0 group-hover:opacity-100 transition-opacity">
                  了解更多 <ChevronRight className="w-3 h-3" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
