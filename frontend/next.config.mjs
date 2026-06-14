/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  async rewrites() {
    // 带 LLM 自定义头的辩论/教练/科普接口由 app/api/debate/*/route.ts 代理转发；
    // 此处仅兜底其余 /api 请求，避免 rewrite 绕过 route handler 导致 x-jh-llm-* 头丢失。
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
