"use client";

import { Brain, Target, BarChart3 } from "lucide-react";

const steps = [
  {
    step: "01",
    icon: Brain,
    title: "AI 多空辩论",
    phase: "思辨",
    desc: "暴露逻辑盲点",
    color: "var(--jh-accent)",
    bg: "var(--jh-accent-dim)",
    glow: "rgba(99, 230, 208, 0.35)",
    // 三角形顶点：顶部
    pos: "top-[4%] left-1/2 -translate-x-1/2",
  },
  {
    step: "02",
    icon: Target,
    title: "策略教练",
    phase: "决策",
    desc: "形成量化策略",
    color: "var(--jh-info)",
    bg: "var(--jh-info-dim)",
    glow: "rgba(124, 184, 255, 0.35)",
    // 三角形顶点：右下
    pos: "bottom-[6%] right-[2%] md:right-[4%]",
  },
  {
    step: "03",
    icon: BarChart3,
    title: "卷宗系统",
    phase: "复盘",
    desc: "追溯持续改进",
    color: "var(--jh-warning)",
    bg: "var(--jh-warning-dim)",
    glow: "rgba(245, 196, 81, 0.35)",
    // 三角形顶点：左下
    pos: "bottom-[6%] left-[2%] md:left-[4%]",
  },
] as const;

/** 等边三角形三条边的箭头路径（viewBox 0 0 400 360） */
const TRIANGLE_EDGES = [
  { d: "M 200 95 L 330 285", delay: "0s", color: "rgba(99,230,208,0.7)" },
  { d: "M 330 285 L 70 285", delay: "0.4s", color: "rgba(124,184,255,0.7)" },
  { d: "M 70 285 L 200 95", delay: "0.8s", color: "rgba(245,196,81,0.7)" },
] as const;

export function WorkflowDiagram() {
  return (
    <section className="mb-16 animate-fade-in-up" style={{ animationDelay: "0.1s" }}>
      <div className="text-center mb-8">
        <p className="text-sm font-semibold text-[var(--jh-text-muted)] uppercase tracking-widest mb-2">
          投资思考闭环
        </p>
        <h2 className="text-xl font-semibold text-[var(--jh-text)]">
          思辨 → 决策 → 复盘，三步形成你的策略
        </h2>
      </div>

      <div className="relative glass-card rounded-2xl p-4 md:p-8 overflow-hidden">
        {/* 三角形闭环图 */}
        <div className="relative mx-auto w-full max-w-lg aspect-[10/9] min-h-[320px] md:min-h-[380px]">
          {/* SVG 三角环 */}
          <svg
            className="absolute inset-0 w-full h-full pointer-events-none"
            viewBox="0 0 400 360"
            preserveAspectRatio="xMidYMid meet"
            aria-hidden
          >
            <defs>
              <linearGradient id="tri-glow" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="rgba(99,230,208,0.15)" />
                <stop offset="50%" stopColor="rgba(124,184,255,0.1)" />
                <stop offset="100%" stopColor="rgba(245,196,81,0.15)" />
              </linearGradient>
              <marker
                id="tri-arrow"
                markerWidth="7"
                markerHeight="7"
                refX="5.5"
                refY="3.5"
                orient="auto"
              >
                <path d="M0,0 L7,3.5 L0,7 Z" fill="rgba(99,230,208,0.65)" />
              </marker>
            </defs>

            {/* 三角形底色 */}
            <polygon
              points="200,95 330,285 70,285"
              fill="url(#tri-glow)"
              stroke="rgba(99,230,208,0.08)"
              strokeWidth="1"
            />

            {/* 三条闭环箭头边 */}
            {TRIANGLE_EDGES.map((edge, i) => (
              <path
                key={i}
                d={edge.d}
                stroke={edge.color}
                strokeWidth="2"
                fill="none"
                markerEnd="url(#tri-arrow)"
                strokeDasharray="8 5"
                className="workflow-dash"
                style={{ animationDelay: edge.delay }}
              />
            ))}

            {/* 中心「闭环」标识 */}
            <circle cx="200" cy="215" r="36" fill="rgba(99,230,208,0.04)" stroke="rgba(99,230,208,0.15)" strokeWidth="1" />
            <text
              x="200"
              y="212"
              textAnchor="middle"
              fill="rgba(99,230,208,0.7)"
              fontSize="11"
              fontWeight="600"
              letterSpacing="2"
            >
              闭环
            </text>
            <text
              x="200"
              y="228"
              textAnchor="middle"
              fill="rgba(148,163,184,0.6)"
              fontSize="8"
            >
              持续改进
            </text>
          </svg>

          {/* 三个节点 */}
          {steps.map((item) => (
            <div key={item.step} className={`absolute ${item.pos} z-10`}>
              <WorkflowNode item={item} />
            </div>
          ))}
        </div>

        <p className="text-center text-xs text-[var(--jh-text-muted)] mt-4 pt-4 border-t border-[var(--jh-border)]">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-[var(--jh-accent)] animate-pulse" />
            卷宗记录每次决策与结果，反哺下一次思辨——形成持续改进的投资闭环
          </span>
        </p>
      </div>
    </section>
  );
}

function WorkflowNode({
  item,
}: {
  item: (typeof steps)[number];
}) {
  const Icon = item.icon;
  return (
    <div className="relative flex flex-col items-center text-center group w-[108px] md:w-[120px]">
      <div
        className="absolute -inset-3 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
        style={{
          background: `radial-gradient(circle at center, ${item.glow} 0%, transparent 70%)`,
        }}
      />
      <div
        className="relative w-12 h-12 md:w-14 md:h-14 rounded-xl flex items-center justify-center mb-2 border border-[var(--jh-border)] transition-transform duration-300 group-hover:scale-105"
        style={{ background: item.bg }}
      >
        <Icon className="w-5 h-5 md:w-6 md:h-6" style={{ color: item.color }} />
        <span
          className="absolute -top-2 -right-2 w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center border"
          style={{
            background: "var(--jh-bg)",
            color: item.color,
            borderColor: item.color,
          }}
        >
          {item.step.replace("0", "")}
        </span>
      </div>
      <span
        className="text-[10px] font-semibold uppercase tracking-widest mb-0.5"
        style={{ color: item.color }}
      >
        {item.phase}
      </span>
      <h3 className="text-xs md:text-sm font-semibold text-[var(--jh-text)] mb-0.5 leading-tight">
        {item.title}
      </h3>
      <p className="text-[10px] md:text-xs text-[var(--jh-text-muted)] leading-snug">
        {item.desc}
      </p>
    </div>
  );
}
