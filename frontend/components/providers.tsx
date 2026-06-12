"use client";

import AppLayout from "@/components/AppLayout";
import { ToastProvider } from "@/components/toast-provider";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      <AppLayout>{children}</AppLayout>
    </ToastProvider>
  );
}
