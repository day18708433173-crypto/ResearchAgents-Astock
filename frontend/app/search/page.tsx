"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Search, TrendingUp, ChevronRight, Building2, Loader2, AlertCircle } from "lucide-react";
import { searchStocks, StockSearchResult } from "@/lib/api";

function SearchFallback() {
  return (
    <div className="min-h-[50vh] bg-[var(--jh-bg)] flex items-center justify-center">
      <Loader2 className="w-6 h-6 animate-spin text-[var(--jh-accent)]" />
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
    if (initialQuery) {
      doSearch(initialQuery);
    }
  }, [initialQuery]);

  const doSearch = async (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    setSearched(true);
    setError("");
    router.replace(`/search?q=${encodeURIComponent(q.trim())}`, { scroll: false });
    try {
      const data = await searchStocks(q.trim());
      setResults(data || []);
    } catch {
      setResults([]);
      setError("搜索失败，请检查网络连接后重试");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    doSearch(query);
  };

  return (
    <div className="min-h-screen bg-[var(--jh-bg)]">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 pt-8 pb-16">
        <h1 className="text-xl font-bold text-[var(--jh-text)] mb-6">股票搜索</h1>

        <form onSubmit={handleSubmit} className="mb-8">
          <div className="relative group">
            <div className="absolute -inset-0.5 bg-gradient-to-r from-[var(--jh-accent)]/20 to-[var(--jh-info)]/20 rounded-[var(--jh-radius-lg)] blur opacity-0 group-focus-within:opacity-100 transition-opacity duration-300" />
            <div className="relative flex flex-col sm:flex-row items-stretch sm:items-center glass-card-accent px-1 py-1 gap-1">
              <div className="flex items-center flex-1 min-w-0">
                <Search className="w-5 h-5 text-[var(--jh-text-muted)] ml-4 flex-shrink-0" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="输入股票名称或代码搜索..."
                  className="flex-1 bg-transparent border-none outline-none text-[var(--jh-text)] placeholder:text-[var(--jh-text-muted)] px-3 py-3 text-sm min-w-0"
                  autoFocus
                  aria-label="搜索股票"
                />
              </div>
              <button type="submit" className="jh-btn-primary flex items-center justify-center gap-1.5 px-5 py-2.5 text-sm mx-1">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                搜索
              </button>
            </div>
          </div>
        </form>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="glass-card p-5">
                <div className="skeleton h-5 w-32 mb-2" />
                <div className="skeleton h-4 w-48" />
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="glass-card p-12 text-center">
            <AlertCircle className="w-10 h-10 text-[var(--jh-danger)] mx-auto mb-3 opacity-60" />
            <p className="text-[var(--jh-text-secondary)] text-sm">{error}</p>
            <button type="button" onClick={() => doSearch(query)} className="jh-btn-primary mt-4 text-sm px-4 py-2">
              重试
            </button>
          </div>
        ) : searched && results.length === 0 ? (
          <div className="glass-card p-12 text-center">
            <Building2 className="w-10 h-10 text-[var(--jh-text-muted)] mx-auto mb-3 opacity-40" />
            <p className="text-[var(--jh-text-secondary)] text-sm">未找到匹配的股票</p>
            <p className="text-[var(--jh-text-muted)] text-xs mt-1">尝试使用股票代码或完整名称搜索</p>
          </div>
        ) : results.length > 0 ? (
          <div className="space-y-3 animate-fade-in-up">
            <p className="text-xs text-[var(--jh-text-muted)] mb-4">找到 {results.length} 个结果</p>
            {results.map((stock, i) => (
              <Link
                key={stock.ts_code}
                href={`/brainstorm?ticker=${encodeURIComponent(stock.ts_code)}&name=${encodeURIComponent(stock.name)}`}
                className="glass-card p-5 block group"
                style={{ animationDelay: `${i * 0.05}s` }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-[var(--jh-accent-dim)] flex items-center justify-center border border-[var(--jh-border-accent)] flex-shrink-0">
                      <TrendingUp className="w-5 h-5 text-[var(--jh-accent)]" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-base font-semibold text-[var(--jh-text)] group-hover:text-[var(--jh-accent)] transition-colors">
                          {stock.name}
                        </h3>
                        <span className="text-xs text-[var(--jh-text-muted)] font-mono">{stock.ts_code}</span>
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        {stock.industry && <span className="jh-badge jh-badge-info text-xs">{stock.industry}</span>}
                        {stock.price != null && (
                          <span className="text-sm text-[var(--jh-text-secondary)] font-mono">¥{stock.price.toFixed(2)}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-[var(--jh-text-muted)] group-hover:text-[var(--jh-accent)] group-hover:translate-x-1 transition-all" />
                </div>
              </Link>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
