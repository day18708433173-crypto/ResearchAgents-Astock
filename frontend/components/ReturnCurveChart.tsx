"use client";

import type { ReturnCurvePoint } from "@/lib/api";

interface ReturnCurveChartProps {
  points: ReturnCurvePoint[];
}

export function ReturnCurveChart({ points }: ReturnCurveChartProps) {
  if (points.length === 0) {
    return (
      <div className="text-sm text-[var(--jh-text-muted)] text-center py-8">
        暂无足够交易数据生成收益曲线
      </div>
    );
  }

  const returns = points.map((p) => p.total_return);
  const min = Math.min(...returns, 0);
  const max = Math.max(...returns, 0);
  const range = max - min || 1;
  const width = 100;
  const height = 48;

  const coords = points.map((p, i) => {
    const x = points.length === 1 ? width / 2 : (i / (points.length - 1)) * width;
    const y = height - ((p.total_return - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  });

  const zeroY = height - ((0 - min) / range) * (height - 4) - 2;

  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-32"
        preserveAspectRatio="none"
        role="img"
        aria-label="累计收益曲线"
      >
        <line
          x1="0"
          y1={zeroY}
          x2={width}
          y2={zeroY}
          stroke="rgba(255,255,255,0.1)"
          strokeWidth="0.3"
        />
        <polyline
          fill="none"
          stroke="var(--jh-accent)"
          strokeWidth="0.8"
          points={coords.join(" ")}
        />
      </svg>
      <div className="flex justify-between text-xs text-[var(--jh-text-muted)] mt-2">
        <span>{points[0]?.date}</span>
        <span>{points[points.length - 1]?.date}</span>
      </div>
    </div>
  );
}
