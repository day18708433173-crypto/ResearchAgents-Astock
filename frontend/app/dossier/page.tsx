"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileText, ChevronRight, Calendar, TrendingUp, FolderOpen, AlertCircle } from "lucide-react";
import { getDossierList, Dossier } from "@/lib/api";

export default function DossierPage() {
  const router = useRouter();
  const [dossiers, setDossiers] = useState<Dossier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadDossiers();
  }, []);

  const loadDossiers = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getDossierList();
      setDossiers(data || []);
    } catch {
      setDossiers([]);
      setError("加载卷宗列表失败，请检查网络后重试");
    } finally {
      setLoading(false);
    }
  };

  const statusConfig: Record<string, { label: string; className: string }> = {
    active: { label: "跟踪中", className: "jh-badge-accent" },
    archived: { label: "已归档", className: "jh-badge-info" },
    draft: { label: "草稿", className: "jh-badge-warning" },
  };

  return (
    <div className="min-h-screen bg-[var(--jh-bg)]">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 pt-8 pb-16">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[var(--jh-text)] mb-1">卷宗</h1>
          <p className="text-sm text-[var(--jh-text-muted)]">管理你的投资策略档案</p>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="glass-card p-5">
                <div className="skeleton h-5 w-40 mb-2" />
                <div className="skeleton h-4 w-60" />
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="glass-card p-12 text-center">
            <AlertCircle className="w-10 h-10 text-[var(--jh-danger)] mx-auto mb-3 opacity-60" />
            <p className="text-sm text-[var(--jh-text-secondary)] mb-4">{error}</p>
            <button type="button" onClick={loadDossiers} className="jh-btn-primary text-sm px-4 py-2">
              重试
            </button>
          </div>
        ) : dossiers.length === 0 ? (
          <div className="glass-card p-16 text-center">
            <div className="w-16 h-16 rounded-2xl bg-[var(--jh-accent-dim)] flex items-center justify-center mx-auto mb-5 border border-[var(--jh-border-accent)]">
              <FolderOpen className="w-8 h-8 text-[var(--jh-accent)] opacity-60" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--jh-text)] mb-2">还没有卷宗</h3>
            <p className="text-sm text-[var(--jh-text-secondary)] mb-6 max-w-xs mx-auto">
              在头脑风暴室完成一次辩论后，策略会自动保存为卷宗
            </p>
            <button
              type="button"
              onClick={() => router.push("/brainstorm")}
              className="jh-btn-primary inline-flex items-center gap-2 text-sm"
            >
              <TrendingUp className="w-4 h-4" />
              开始第一次辩论
            </button>
          </div>
        ) : (
          <div className="space-y-3 animate-fade-in-up">
            {dossiers.map((d, i) => {
              const statusKey = d.current_strategy_version > 0 ? "active" : "draft";
              const status = statusConfig[statusKey];
              return (
                <Link
                  key={d.dossier_id}
                  href={`/dossier/${d.dossier_id}`}
                  className="glass-card p-5 block group"
                  style={{ animationDelay: `${i * 0.05}s` }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-lg bg-[var(--jh-accent-dim)] flex items-center justify-center border border-[var(--jh-border-accent)] flex-shrink-0">
                        <FileText className="w-5 h-5 text-[var(--jh-accent)]" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2.5">
                          <h3 className="text-base font-semibold text-[var(--jh-text)] group-hover:text-[var(--jh-accent)] transition-colors">
                            {d.stock_name}
                          </h3>
                          <span className="text-xs text-[var(--jh-text-muted)] font-mono">{d.stock_code}</span>
                        </div>
                        <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                          {d.industry && <span className="jh-badge jh-badge-info text-xs">{d.industry}</span>}
                          <span className={`jh-badge text-xs ${status.className}`}>{status.label}</span>
                          <span className="flex items-center gap-1 text-xs text-[var(--jh-text-muted)]">
                            <Calendar className="w-3 h-3" />
                            {d.updated_at ? new Date(d.updated_at).toLocaleDateString("zh-CN") : "-"}
                          </span>
                        </div>
                      </div>
                    </div>
                    <ChevronRight className="w-5 h-5 text-[var(--jh-text-muted)] group-hover:text-[var(--jh-accent)] group-hover:translate-x-1 transition-all" />
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
