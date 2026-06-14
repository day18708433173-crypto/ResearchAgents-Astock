/**
 * 辩论 SSE 地址：本地开发优先直连后端，避免 Next.js 代理缓冲导致「一次性出字」。
 */
export function buildDebateSseUrl(apiPath: string): string {
  const path = apiPath.startsWith('/') ? apiPath : `/${apiPath}`;

  if (typeof window === 'undefined') {
    return path;
  }

  const envBase = process.env.NEXT_PUBLIC_BACKEND_URL?.trim().replace(/\/+$/, '');
  if (envBase) {
    return `${envBase}${path}`;
  }

  const { hostname } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return `http://localhost:8000${path}`;
  }

  return path;
}
