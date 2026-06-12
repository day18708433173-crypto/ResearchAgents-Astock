import { NextRequest, NextResponse } from 'next/server';
import { BACKEND_URL as BACKEND } from '@/lib/backend';

export async function POST(
  request: NextRequest,
  { params }: { params: { debate_id: string } },
) {
  const debateId = params.debate_id;

  try {
    const body = await request.json();
    const response = await fetch(`${BACKEND}/api/debate/${encodeURIComponent(debateId)}/coach-transcript`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch {
    return NextResponse.json({ detail: '无法连接辩论历史服务' }, { status: 503 });
  }
}
