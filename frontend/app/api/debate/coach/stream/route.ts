/**
 * 策略教练 SSE 流式代理路由
 */

import { BACKEND_URL } from "@/lib/backend";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const targetUrl = `${BACKEND_URL}/api/debate/coach/stream`;

    const response = await fetch(targetUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(
        JSON.stringify({ error: errorText || `后端错误: ${response.status}` }),
        { status: response.status, headers: { "Content-Type": "application/json" } }
      );
    }

    return new Response(response.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    console.error("[Coach Stream Proxy] 连接后端失败:", error);
    return new Response(
      JSON.stringify({ error: "策略教练流式服务连接失败" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}
