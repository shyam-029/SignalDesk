// Server state via TanStack Query. One hook per backend endpoint.
// Keys are structured so caches dedupe across pages (e.g. the landing preview
// and the stock page share the same RELIANCE.NS detail entry).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type ScreenerParams } from "@/lib/api";
import type { ExplainQuestionType } from "@/lib/types";

export const PRICE_RANGES = ["1mo", "3mo", "6mo", "1y", "2y"] as const;
export type PriceRange = (typeof PRICE_RANGES)[number];

export const PRICE_RANGE_LABELS: Record<PriceRange, string> = {
  "1mo": "1M",
  "3mo": "3M",
  "6mo": "6M",
  "1y": "1Y",
  "2y": "2Y",
};

export function useStockList(
  page = 1,
  limit = 50,
  sector?: string,
  sort?: string,
  direction?: string,
) {
  return useQuery({
    queryKey: ["stocks", page, limit, sector ?? null, sort ?? null, direction ?? null],
    queryFn: () => api.stocks(page, limit, sector, sort, direction),
    staleTime: 60_000,
  });
}

export function useStockDetail(symbol: string) {
  return useQuery({
    queryKey: ["stock-detail", symbol],
    queryFn: () => api.stockDetail(symbol),
    staleTime: 60_000,
    retry: (failureCount, error) => {
      // Unknown symbols resolve instantly, so don't hammer the API with retries.
      const status = (error as { status?: number }).status;
      if (status === 404) return false;
      return failureCount < 2;
    },
  });
}

export function usePrices(symbol: string, range: string) {
  return useQuery({
    queryKey: ["prices", symbol, range],
    queryFn: () => api.prices(symbol, range),
    staleTime: 5 * 60_000,
  });
}

export function useFundamentals(symbol: string) {
  return useQuery({
    queryKey: ["fundamentals", symbol],
    queryFn: () => api.fundamentals(symbol),
    staleTime: 10 * 60_000,
  });
}

export function useScores(symbol: string) {
  return useQuery({
    queryKey: ["scores", symbol],
    queryFn: () => api.scores(symbol),
    staleTime: 60_000,
  });
}

export const VALUATION_METRICS = ["PE", "EV_EBITDA", "PB", "PS"] as const;
export type ValuationMetric = (typeof VALUATION_METRICS)[number];

export function useValuation(symbol: string, metric: string = "PE") {
  return useQuery({
    queryKey: ["valuation", symbol, metric],
    queryFn: () => api.valuation(symbol, metric),
    staleTime: 60_000,
    retry: (failureCount, error) => {
      const code = (error as { code?: string }).code;
      if (code === "NO_PEERS" || code === "INSUFFICIENT_DATA") return false;
      return failureCount < 2;
    },
  });
}

export function useAlpha(symbol: string) {
  return useQuery({
    queryKey: ["alpha", symbol],
    queryFn: () => api.alpha(symbol),
    staleTime: 60_000,
  });
}

export function useTechnicals(symbol: string) {
  return useQuery({
    queryKey: ["technicals", symbol],
    queryFn: () => api.technicals(symbol),
    staleTime: 60_000,
  });
}

export function useNews(symbol: string, limit = 12) {
  return useQuery({
    queryKey: ["news", symbol, limit],
    queryFn: () => api.news(symbol, limit),
    staleTime: 2 * 60_000,
  });
}

export function useSentiment(symbol: string) {
  return useQuery({
    queryKey: ["sentiment", symbol],
    queryFn: () => api.sentiment(symbol),
    staleTime: 2 * 60_000,
  });
}

export function useScreener(params: ScreenerParams) {
  return useQuery({
    queryKey: ["screener", params],
    queryFn: () => api.screener(params),
    staleTime: 60_000,
  });
}

export function useExplain(symbol: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (questionType: ExplainQuestionType) =>
      api.explain(symbol, questionType),
    // Explanations are deterministic per day (TTL-cached server-side), so a
    // successful fetch is stored in the query cache under an explain key.
    onSuccess: (data) => {
      queryClient.setQueryData(
        ["explain", data.symbol, data.question_type],
        data.explanation,
      );
    },
  });
}

// Part H: grounded single-shot ask. One question at a time, no history —
// never retried automatically (a rate-limit/cap answer should surface as-is).
export function useAsk(symbol: string) {
  return useMutation({
    mutationFn: (question: string) => api.ask(symbol, question),
    retry: false,
  });
}

// --- Historical research (Phase 6.5 Part E endpoints) ------------------------

/** Never retry 404s (unknown symbol resolves instantly). */
function noRetryOn404(failureCount: number, error: Error): boolean {
  const status = (error as { status?: number }).status;
  if (status === 404) return false;
  return failureCount < 2;
}

export function usePerformance(symbol: string) {
  return useQuery({
    queryKey: ["performance", symbol],
    queryFn: () => api.performance(symbol),
    staleTime: 5 * 60_000,
    retry: noRetryOn404,
  });
}

export function useAlphaHistory(symbol: string, limit = 180) {
  return useQuery({
    queryKey: ["alpha-history", symbol, limit],
    queryFn: () => api.alphaHistory(symbol, limit),
    staleTime: 10 * 60_000,
    retry: noRetryOn404,
  });
}

export function useTechnicalsSeries(symbol: string, limit = 250) {
  return useQuery({
    queryKey: ["technicals-series", symbol, limit],
    queryFn: () => api.technicalsSeries(symbol, limit),
    staleTime: 10 * 60_000,
    retry: noRetryOn404,
  });
}

export function usePeers(symbol: string) {
  return useQuery({
    queryKey: ["peers", symbol],
    queryFn: () => api.peers(symbol),
    staleTime: 10 * 60_000,
    retry: noRetryOn404,
  });
}

export function useFinancialsHistory(
  symbol: string,
  periodType: "annual" | "quarterly" = "annual",
) {
  return useQuery({
    queryKey: ["financials-history", symbol, periodType],
    queryFn: () => api.financialsHistory(symbol, periodType),
    staleTime: 30 * 60_000,
    retry: noRetryOn404,
  });
}
