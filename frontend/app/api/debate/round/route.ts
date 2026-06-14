/**
 * SSE 单轮辩论代理：转发 x-jh-llm-* 自定义头到后端
 */

import { BACKEND_URL } from '@/lib/backend';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function llmHeaders(request: Request): HeadersInit {
  const headers: Record<string, string> = {};
  for (const name of [
    'x-jh-llm-api-key',
    'x-jh-llm-base-url',
    'x-jh-llm-model',
    'x-jh-llm-reasoning-model',
  ]) {
    const value = request.headers.get(name);
    if (value) headers[name] = value;
  }
  return headers;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const ticker = searchParams.get('ticker');

  if (!ticker) {
    return new Response(JSON.stringify({ error: '缺少 ticker 参数' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const targetUrl = `${BACKEND_URL}/api/debate/round?${searchParams.toString()}`;

  try {
    const response = await fetch(targetUrl, {
      headers: {
        Accept: 'text/event-stream',
        'Cache-Control': 'no-cache',
        ...llmHeaders(request),
      },
    });

    if (!response.ok) {
      const text = await response.text();
      return new Response(text || JSON.stringify({ error: `后端错误: ${response.status}` }), {
        status: response.status,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(response.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    });
  } catch (error) {
    console.error('[Round SSE Proxy] 连接后端失败:', error);
    return new Response(JSON.stringify({ error: '连接后端失败' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
