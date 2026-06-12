"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Brain, FileText, Home, Sparkles } from "lucide-react";

const navItems = [
  { href: "/", label: "首页", icon: Home },
  { href: "/brainstorm", label: "头脑风暴", icon: Brain },
  { href: "/dossier", label: "卷宗", icon: FileText },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-[var(--jh-bg)]">
      <header className="sticky top-0 z-50 border-b border-[var(--jh-border)] bg-[var(--jh-bg)]/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="w-8 h-8 rounded-lg bg-[var(--jh-accent-dim)] flex items-center justify-center border border-[var(--jh-border-accent)] group-hover:border-[var(--jh-accent)]/40 transition-colors">
              <Sparkles className="w-4 h-4 text-[var(--jh-accent)]" />
            </div>
            <span className="text-base font-bold text-[var(--jh-text)] tracking-tight">镜衡</span>
          </Link>

          <nav className="flex items-center gap-1">
            {navItems.map((item) => {
              const isActive =
                pathname === item.href ||
                (item.href !== "/" && pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2 px-2.5 sm:px-3.5 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? "bg-[var(--jh-accent-dim)] text-[var(--jh-accent)]"
                      : "text-[var(--jh-text-secondary)] hover:text-[var(--jh-text)] hover:bg-[rgba(255,255,255,0.04)]"
                  }`}
                >
                  <item.icon className="w-4 h-4" />
                  <span className="hidden sm:inline">{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      <main>{children}</main>
    </div>
  );
}
