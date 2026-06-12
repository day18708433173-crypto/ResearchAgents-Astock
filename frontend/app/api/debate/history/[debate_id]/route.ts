import { NextRequest, NextResponse } from 'next/server';
import { BACKEND_URL as BACKEND } from '@/lib/backend';

export async function GET(
  _request: NextRequest,
  { params }: { params: { debate_id: string } },
) {
  const debateId = params.debate_id;

  try {
    const response = await fetch(`${BACKEND}/api/debate/history/${encodeURIComponent(debateId)}`, {
      cache: 'no-store',
    });

    if (!response.ok) {
      return NextResponse.json(
        { detail: '辩论记录不存在' },
        { status: response.status },
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ detail: '无法连接辩论历史服务' }, { status: 503 });
  }
}
