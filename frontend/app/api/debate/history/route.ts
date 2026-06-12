import { NextRequest, NextResponse } from 'next/server';
import { BACKEND_URL } from '@/lib/backend';

export async function GET(request: NextRequest) {
  const limit = request.nextUrl.searchParams.get('limit') || '6';

  try {
    const response = await fetch(`${BACKEND_URL}/api/debate/history?limit=${encodeURIComponent(limit)}`, {
      cache: 'no-store',
    });

    if (!response.ok) {
      return NextResponse.json([]);
    }

    const data = await response.json();
    return NextResponse.json(Array.isArray(data) ? data : []);
  } catch {
    return NextResponse.json([]);
  }
}
