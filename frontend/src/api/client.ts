import type { PackageProblemDto, ProblemDto, SolveJobDto, SolveQueuedDto, SolveRequestDto } from './dtos';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '';

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body != null && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, messageFromBody(body) ?? response.statusText, body);
  }
  return body as T;
}

function messageFromBody(body: unknown): string | undefined {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    return 'Request validation failed';
  }
  if (body && typeof body === 'object' && 'message' in body) {
    const message = (body as { message: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return undefined;
}

export const apiClient = {
  getDefaultProblem: (init?: RequestInit) => request<ProblemDto>('/api/problem/default', init),
  uploadPackage: (payload: unknown) =>
    request<PackageProblemDto>('/api/problem/package', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  startSolve: (payload: SolveRequestDto) =>
    request<SolveQueuedDto>('/api/solve', { method: 'POST', body: JSON.stringify(payload) }),
  getSolveJob: (jobId: string, init?: RequestInit) =>
    request<SolveJobDto>(`/api/solve/${encodeURIComponent(jobId)}`, init),
};
