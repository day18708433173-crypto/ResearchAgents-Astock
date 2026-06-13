/**
 * 策略教练对话代理路由
 * 将前端的POST请求代理到后端8000端口
 */

import { BACKEND_URL } from '@/lib/backend';

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

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const targetUrl = `${BACKEND_URL}/api/debate/coach`;
    
    console.log('[Coach Proxy] 代理请求到:', targetUrl);
    console.log('[Coach Proxy] 请求体:', JSON.stringify(body).substring(0, 500));
    
    const res = await fetch(targetUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...llmHeaders(request) },
      body: JSON.stringify(body),
    });
    
    const responseText = await res.text();
    console.log('[Coach Proxy] 后端响应状态:', res.status);
    console.log('[Coach Proxy] 后端响应:', responseText.substring(0, 500));
    
    return new Response(responseText, {
      status: res.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('[Coach Proxy] 代理失败:', error);
    return new Response(JSON.stringify({ detail: '策略教练服务连接失败', error: String(error) }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
