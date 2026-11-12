// The whole screened universe, client-side: four cached screener pages of
// 250. Used wherever a page needs to reason about every company at once (the
// market map, the sector board, the screener's summary). The query keys are
// identical everywhere, so the pages are fetched once and shared.

import * as React from "react";
import { useQueries } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { ScreenResult } from "@/lib/types";

const PAGES = [1, 2, 3, 4];

export function useScreenerUniverse() {
  const results = useQueries({
    queries: PAGES.map((page) => {
      const params = { page, limit: 250 };
      return {
        queryKey: ["screener", params],
        queryFn: () => api.screener(params),
        staleTime: 10 * 60_000,
      };
    }),
  });
  const loadedKey = results.map((q) => q.dataUpdatedAt).join("-");
  const rows = React.useMemo<ScreenResult[]>(
    () => results.flatMap((q) => q.data?.items ?? []),
    [loadedKey], // eslint-disable-line react-hooks/exhaustive-deps
  );
  return {
    rows,
    isLoading: results.some((q) => q.isLoading),
    /** True once every page has arrived, so totals are complete. */
    isComplete: results.every((q) => q.data != null),
  };
}

/** The screener's filters as a plain predicate over one row. */
export interface ScreenFilter {
  status: string;
  sector: string;
  industry: string;
  minProfitability: number | null;
  minSolvency: number | null;
}

export function matchesFilter(r: ScreenResult, f: ScreenFilter): boolean {
  if (f.status && r.valuation_status !== f.status) return false;
  if (f.sector && r.sector !== f.sector) return false;
  if (f.industry && r.industry !== f.industry) return false;
  if (f.minProfitability != null && (r.profitability == null || r.profitability < f.minProfitability)) {
    return false;
  }
  if (f.minSolvency != null && (r.solvency == null || r.solvency < f.minSolvency)) return false;
  return true;
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
