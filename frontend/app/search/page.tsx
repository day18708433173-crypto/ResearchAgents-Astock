"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, ArrowRight, Building2, Loader2, Search } from "lucide-react";
import { searchStocks, type StockSearchResult } from "@/lib/api";

function SearchFallback() {
  return (
    <div className="min-h-[50vh] flex items-center justify-center bg-[var(--jh-bg)]">
      <Loader2 className="w-5 h-5 animate-spin text-[var(--jh-text-muted)]" />
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<SearchFallback />}>
      <SearchPageContent />
    </Suspense>
  );
}

function SearchPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") || "";

  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (initialQuery) void doSearch(initialQuery);
  }, [initialQuery]);

  const doSearch = async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    setLoading(true);
    setSearched(true);
    setError("");
    router.replace(`/search?q=${encodeURIComponent(trimmed)}`, { scroll: false });
    try {
      const data = await searchStocks(trimmed);
      setResults(data || []);
    } catch {
      setResults([]);
      setError("搜索失败，请检查数据服务后重试");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void doSearch(query);
  };

  return (
    <div className="min-h-[calc(100vh-3.5rem)] bg-[var(--jh-bg)]">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 py-6">
        <div className="mb-5">
          <div className="text-xs uppercase tracking-[0.18em] text-[var(--jh-text-muted)]">Command Search</div>
          <h1 className="mt-2 text-2xl font-semibold text-[var(--jh-text)]">打开研究对象</h1>
          <p className="mt-1 text-sm text-[var(--jh-text-secondary)]">
            按名称或代码定位 A 股标的，进入研究台后建立观点、策略和复盘记录。
          </p>
        </div>

        <form onSubmit={handleSubmit} className="terminal-panel-strong mb-5 p-3">
          <div className="flex items-center gap-3">
            <Search className="w-5 h-5 text-[var(--jh-text-muted)]" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="例如：贵州茅台、600519、宁德时代"
              className="min-w-0 flex-1 bg-transparent text-base text-[var(--jh-text)] placeholder:text-[var(--jh-text-muted)] outline-none"
              autoFocus
              aria-label="搜索股票"
            />
            <button type="submit" className="jh-btn-primary h-9 px-4 text-sm" disabled={loading}>
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "搜索"}
            </button>
          </div>
        </form>

        <section className="terminal-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--jh-border)] px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-[var(--jh-text)]">匹配结果</h2>
              <p className="text-xs text-[var(--jh-text-muted)]">
                {searched ? `找到 ${results.length} 个结果` : "等待输入查询"}
              </p>
            </div>
          </div>

          {loading ? (
            <div className="p-4 space-y-2">
              {[1, 2, 3].map((item) => (
                <div key={item} className="skeleton h-11 w-full" />
              ))}
            </div>
          ) : error ? (
            <div className="p-8 text-center">
              <AlertCircle className="mx-auto mb-3 w-8 h-8 text-[var(--jh-danger)]" />
              <p className="text-sm text-[var(--jh-text-secondary)]">{error}</p>
              <button type="button" onClick={() => void doSearch(query)} className="jh-btn-secondary mt-4 px-4 py-2 text-sm">
                重试
              </button>
            </div>
          ) : searched && results.length === 0 ? (
            <div className="p-10 text-center">
              <Building2 className="mx-auto mb-3 w-8 h-8 text-[var(--jh-text-muted)]" />
              <p className="text-sm text-[var(--jh-text-secondary)]">未找到匹配股票</p>
              <p className="mt-1 text-xs text-[var(--jh-text-muted)]">尝试使用完整股票名称或六位代码。</p>
            </div>
          ) : results.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>标的</th>
                    <th>代码</th>
                    <th>行业</th>
                    <th>参考价</th>
                    <th>动作</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((stock) => (
                    <tr key={stock.ts_code}>
                      <td>
                        <div className="font-medium text-[var(--jh-text)]">{stock.name}</div>
                      </td>
                      <td className="font-mono text-xs">{stock.ts_code}</td>
                      <td>{stock.industry || "-"}</td>
                      <td className="numeric">{stock.price != null ? `¥${stock.price.toFixed(2)}` : "-"}</td>
                      <td>
                        <Link
                          href={`/brainstorm?ticker=${encodeURIComponent(stock.ts_code)}&name=${encodeURIComponent(stock.name)}`}
                          className="inline-flex items-center gap-1 text-xs text-[var(--jh-accent)] hover:text-[var(--jh-accent-2)]"
                        >
                          进入研究台 <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-sm text-[var(--jh-text-muted)]">
              输入标的名称或代码后，结果将在这里以表格形式展示。
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
