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
  title: "镜衡 · 投研工作台",
  description: "面向长期跟踪的投资研究工作台，沉淀多空证据、策略版本、交易记录与复盘结论。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[#080A0D] text-[#e7eaee]`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
