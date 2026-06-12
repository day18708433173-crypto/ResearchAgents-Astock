import type { Metadata } from "next";
import localFont from "next/font/local";
import { Providers } from "@/components/providers";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});

const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "镜衡 · 照见盲点，衡定策略",
  description: "AI辩论暴露逻辑盲点，策略教练引导形成量化策略，卷宗系统让每笔交易有据可循。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[#0B0F14] text-[#eef2ff]`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
