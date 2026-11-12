// Nifty 50 constituents, mirrored from the backend seed list
// (backend/app/data/nifty250.py, official NSE list downloaded 2026-09-06).
// The API has no index-membership filter, so the landing page asks for the
// largest ranked companies and keeps the ones on this list. Refresh this set
// when the backend seed list is refreshed.

import { useStockList } from "@/lib/hooks";

export const NIFTY_50: ReadonlySet<string> = new Set([
  "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
  "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
  "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
  "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
  "HINDUNILVR", "ICICIBANK", "ITC", "INFY", "INDIGO",
  "JSWSTEEL", "JIOFIN", "KOTAKBANK", "LT", "M&M",
  "MARUTI", "MAXHEALTH", "NTPC", "NESTLEIND", "ONGC",
  "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN",
  "SUNPHARMA", "TCS", "TATACONSUM", "TMPV", "TATASTEEL",
  "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]);

export function isNifty50(symbol: string): boolean {
  return NIFTY_50.has(symbol.replace(/\.NS$/, ""));
}

/**
 * The Nifty 50 with today's stored close and move, largest first.
 *
 * Two requests, both shared by query key with the rest of the app:
 *   - the 50 largest companies: this is the list the landing snapshot
 *     pre-loads, so most constituents paint immediately;
 *   - the 150 largest: comfortably contains every constituent, and replaces
 *     the first list when it arrives.
 * Stocks without a stored move are left out rather than shown as zero.
 */
export function useNifty50() {
  const quick = useStockList(1, 50, undefined, "market_cap", "desc");
  const full = useStockList(1, 150, undefined, "market_cap", "desc");
  const source = full.data ?? quick.data;
  const items = (source?.items ?? []).filter(
    (s) => isNifty50(s.symbol) && s.change_pct != null,
  );
  return {
    items,
    data: source,
    isLoading: !source && (quick.isLoading || full.isLoading),
    error: source ? null : (full.error ?? quick.error),
    refetch: () => {
      void quick.refetch();
      void full.refetch();
    },
  };
}
