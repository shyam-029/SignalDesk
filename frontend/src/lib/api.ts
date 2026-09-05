// Centralized API client: every request goes through here.
//
// The backend returns errors in a single envelope (PLANNING §11):
//   { "error": { "code", "message", "detail", "request_id" } }
// We parse that into ApiError so the UI can branch on the code (e.g. 404 →
// "unknown symbol") instead of string-matching messages.

import type {
  AlphaHistoryResponse,
  AlphaResponse,
  ExplainQuestionType,
  ExplainResponse,
  FinancialsHistoryResponse,
  Fundamentals,
  NewsListResponse,
  PeersResponse,
  PerformanceResponse,
  PriceHistory,
  ScoreCard,
  ScreenerResponse,
  Sentiment,
  StockDetail,
  StockListResponse,
  Technicals,
  TechnicalsSeriesResponse,
  Valuation,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: Record<string, unknown>;

  constructor(status: number, code: string, message: string, detail: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }

  get isNotFound(): boolean {
    return this.status === 404 || this.code === "RESOURCE_NOT_FOUND";
  }

  get isInsufficientData(): boolean {
    return this.code === "INSUFFICIENT_DATA";
  }

  get isNoPeers(): boolean {
    return this.code === "NO_PEERS";
  }
}

// Default is same-origin ("/api/v1"): the Vite dev server proxies /api to
// FastAPI. Set VITE_API_BASE for direct or production API locations.
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

async function parseError(response: Response): Promise<ApiError> {
  let code = `HTTP_${response.status}`;
  let message = response.statusText || "Request failed";
  let detail: Record<string, unknown> = {};
  try {
    const body = (await response.json()) as { error?: { code?: string; message?: string; detail?: Record<string, unknown> } };
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      detail = body.error.detail ?? {};
    }
  } catch {
    // Non-JSON error body: keep the HTTP fallbacks above.
  }
  return new ApiError(response.status, code, message, detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    // fetch only rejects on network-level failures (backend down, offline).
    throw new ApiError(0, "NETWORK_ERROR", "Could not reach the SignalDesk API.");
  }
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// --- Endpoint helpers (one per backend route the frontend uses) -------------

export const api = {
  stocks: (page = 1, limit = 50, sector?: string) => {
    const q = new URLSearchParams({ page: String(page), limit: String(limit) });
    if (sector) q.set("sector", sector);
    return apiGet<StockListResponse>(`/stocks?${q.toString()}`);
  },

  stockDetail: (symbol: string) =>
    apiGet<StockDetail>(`/stocks/${encodeURIComponent(symbol)}`),

  prices: (symbol: string, range: string) =>
    apiGet<PriceHistory>(
      `/stocks/${encodeURIComponent(symbol)}/prices?range=${encodeURIComponent(range)}&resample=1d`,
    ),

  fundamentals: (symbol: string) =>
    apiGet<Fundamentals>(`/stocks/${encodeURIComponent(symbol)}/fundamentals`),

  scores: (symbol: string) => apiGet<ScoreCard>(`/stocks/${encodeURIComponent(symbol)}/scores`),

  valuation: (symbol: string, metric: string) =>
    apiGet<Valuation>(
      `/stocks/${encodeURIComponent(symbol)}/valuation?metric=${encodeURIComponent(metric)}`,
    ),

  alpha: (symbol: string) => apiGet<AlphaResponse>(`/stocks/${encodeURIComponent(symbol)}/alpha`),

  technicals: (symbol: string) =>
    apiGet<Technicals>(`/stocks/${encodeURIComponent(symbol)}/technicals`),

  news: (symbol: string, limit = 20) =>
    apiGet<NewsListResponse>(`/stocks/${encodeURIComponent(symbol)}/news?limit=${limit}`),

  sentiment: (symbol: string) =>
    apiGet<Sentiment>(`/stocks/${encodeURIComponent(symbol)}/sentiment`),

  screener: (params: ScreenerParams) => {
    const q = new URLSearchParams({ page: String(params.page), limit: String(params.limit) });
    if (params.status) q.set("status", params.status);
    if (params.minProfitability != null) q.set("min_profitability", String(params.minProfitability));
    if (params.minSolvency != null) q.set("min_solvency", String(params.minSolvency));
    return apiGet<ScreenerResponse>(`/screener?${q.toString()}`);
  },

  explain: (symbol: string, questionType: ExplainQuestionType) =>
    apiPost<ExplainResponse>(`/stocks/${encodeURIComponent(symbol)}/explain`, {
      question_type: questionType,
    }),

  // --- Historical research (Phase 6.5 Part E) ---

  performance: (symbol: string) =>
    apiGet<PerformanceResponse>(
      `/stocks/${encodeURIComponent(symbol)}/performance`,
    ),

  alphaHistory: (symbol: string, limit = 180) =>
    apiGet<AlphaHistoryResponse>(
      `/stocks/${encodeURIComponent(symbol)}/alpha/history?limit=${limit}`,
    ),

  technicalsSeries: (symbol: string, limit = 250) =>
    apiGet<TechnicalsSeriesResponse>(
      `/stocks/${encodeURIComponent(symbol)}/technicals/series?limit=${limit}`,
    ),

  peers: (symbol: string) =>
    apiGet<PeersResponse>(`/stocks/${encodeURIComponent(symbol)}/peers`),

  financialsHistory: (symbol: string, periodType?: "annual" | "quarterly") => {
    const q = new URLSearchParams();
    if (periodType) q.set("period_type", periodType);
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return apiGet<FinancialsHistoryResponse>(
      `/stocks/${encodeURIComponent(symbol)}/financials/history${suffix}`,
    );
  },
};

export interface ScreenerParams {
  status?: string | null;
  minProfitability?: number | null;
  minSolvency?: number | null;
  page?: number;
  limit?: number;
}
