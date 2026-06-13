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
  const areaPoints = `0,${zeroY} ${coords.join(" ")} ${width},${zeroY}`;
  const lastPoint = points[points.length - 1];
  const lastReturn = lastPoint?.total_return ?? 0;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs text-[var(--jh-text-muted)]">累计收益</div>
          <div className={`text-lg font-semibold numeric ${lastReturn >= 0 ? "text-[var(--jh-accent)]" : "text-[var(--jh-danger)]"}`}>
            {lastReturn >= 0 ? "+" : ""}¥{Math.round(lastReturn).toLocaleString()}
          </div>
        </div>
        <div className="text-right text-xs text-[var(--jh-text-muted)]">
          <div>区间高点 ¥{Math.round(max).toLocaleString()}</div>
          <div>区间低点 ¥{Math.round(min).toLocaleString()}</div>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-40"
        preserveAspectRatio="none"
        role="img"
        aria-label="累计收益曲线"
      >
        {[12, 24, 36].map((y) => (
          <line
            key={y}
            x1="0"
            y1={y}
            x2={width}
            y2={y}
            stroke="rgba(255,255,255,0.06)"
            strokeWidth="0.2"
          />
        ))}
        <line
          x1="0"
          y1={zeroY}
          x2={width}
          y2={zeroY}
          stroke="rgba(255,255,255,0.16)"
          strokeWidth="0.35"
        />
        <polygon
          fill={lastReturn >= 0 ? "rgba(143,212,195,0.10)" : "rgba(223,95,95,0.10)"}
          points={areaPoints}
        />
        <polyline
          fill="none"
          stroke={lastReturn >= 0 ? "var(--jh-accent)" : "var(--jh-danger)"}
          strokeWidth="0.65"
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
