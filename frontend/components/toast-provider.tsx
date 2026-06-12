"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { X, AlertCircle, CheckCircle2, Info } from "lucide-react";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({
  toast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

let toastId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((message: string, type: ToastType = "info") => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const dismiss = (id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const iconMap = {
    success: CheckCircle2,
    error: AlertCircle,
    info: Info,
  };

  const colorMap = {
    success: "border-[var(--jh-accent)]/30 bg-[rgba(99,230,208,0.1)] text-[var(--jh-accent)]",
    error: "border-[var(--jh-danger)]/30 bg-[rgba(255,122,122,0.1)] text-[var(--jh-danger)]",
    info: "border-[var(--jh-info)]/30 bg-[rgba(124,184,255,0.1)] text-[var(--jh-info)]",
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        className="fixed bottom-6 right-6 z-[100] flex flex-col gap-2 max-w-sm pointer-events-none"
        aria-live="polite"
        aria-atomic="true"
      >
        {toasts.map((t) => {
          const Icon = iconMap[t.type];
          return (
            <div
              key={t.id}
              className={`pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg backdrop-blur-sm text-sm text-[var(--jh-text)] animate-fade-in-up ${colorMap[t.type]}`}
              role="status"
            >
              <Icon className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span className="flex-1">{t.message}</span>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                className="opacity-60 hover:opacity-100 transition-opacity"
                aria-label="关闭通知"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
