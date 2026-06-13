import { NextRequest, NextResponse } from 'next/server';
import { BACKEND_URL } from '@/lib/backend';

function llmHeaders(request: NextRequest): HeadersInit {
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

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    console.log('[Knowledge API Proxy] Received request:', JSON.stringify(body, null, 2));
    
    const backendUrl = `${BACKEND_URL}/api/debate/knowledge`;
    
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...llmHeaders(request),
      },
      body: JSON.stringify(body),
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('[Knowledge API Proxy] Backend error:', response.status, errorText);
      return NextResponse.json(
        { detail: `知识科普失败: ${errorText}` },
        { status: response.status }
      );
    }
    
    const data = await response.json();
    console.log('[Knowledge API Proxy] Success:', JSON.stringify(data, null, 2).slice(0, 200));
    
    return NextResponse.json(data);
  } catch (error) {
    console.error('[Knowledge API Proxy] Error:', error);
    return NextResponse.json(
      { detail: '知识科普请求失败' },
      { status: 500 }
    );
  }
}
