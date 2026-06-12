/**
 * SSE流式辩论代理路由
 * 将前端的SSE请求代理到后端8000端口
 */

import { BACKEND_URL } from '@/lib/backend';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const ticker = searchParams.get('ticker');
  const ticker_name = searchParams.get('ticker_name');
  
  if (!ticker) {
    return new Response(JSON.stringify({ error: '缺少ticker参数' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  
  const params = new URLSearchParams({ ticker, ticker_name: ticker_name || '' });

  const targetUrl = `${BACKEND_URL}/api/debate/stream?${params.toString()}`;
  
  console.log('[SSE Proxy] 代理请求到:', targetUrl);
  
  try {
    const response = await fetch(targetUrl, {
      headers: {
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
    });
    
    if (!response.ok) {
      console.error('[SSE Proxy] 后端响应错误:', response.status);
      return new Response(JSON.stringify({ error: `后端错误: ${response.status}` }), {
        status: response.status,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    
    // 返回SSE流
    return new Response(response.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  } catch (error) {
    console.error('[SSE Proxy] 连接后端失败:', error);
    return new Response(JSON.stringify({ error: '连接后端失败' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
