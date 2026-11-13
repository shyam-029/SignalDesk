// Per-stock page snapshots (2026-11-12).
//
// After each nightly, .github/workflows/ingest.yml (stock-snapshots job) writes one file
// per listed stock to a private R2 bucket, and the Cloudflare Worker serves
// it at /snapshot/stock/<SYMBOL>.json (frontend/worker/index.js). The file
// has the landing snapshot's format: each API response under the TanStack
// Query key its hook uses. Seeding the cache from it lets a first-time
// visitor see the page at once, even while the Render API is waking; the
// hooks still refresh from the API in the background, exactly as with the
// landing snapshot.
//
// Loaded as early as possible: at app start for a direct visit to a stock
// URL (in parallel with the page's code chunk), and on in-app navigation
// from the stock page itself. Each symbol is fetched at most once per visit.
// A missing file (a stock outside the nightly list), or any error, changes
// nothing: the page loads from the API as before.

import type { QueryClient } from "@tanstack/react-query";

import { applyLandingSnapshot } from "@/lib/landingSnapshot";
import { normalizeSymbol } from "@/lib/utils";

export function stockSnapshotUrl(symbol: string): string {
  return `/snapshot/stock/${encodeURIComponent(normalizeSymbol(symbol))}.json`;
}

const requested = new Set<string>();

/** Test hook: forget which symbols were already fetched. */
export function resetStockSnapshots(): void {
  requested.clear();
}

/** Fetch one stock's snapshot and seed the cache. Never throws. */
export async function loadStockSnapshot(
  client: QueryClient,
  symbol: string,
  fetchImpl: typeof fetch = fetch,
): Promise<number> {
  const canonical = normalizeSymbol(symbol);
  if (!canonical || requested.has(canonical)) return 0;
  requested.add(canonical);
  try {
    const res = await fetchImpl(stockSnapshotUrl(canonical));
    if (!res.ok || !(res.headers.get("content-type") ?? "").includes("json")) return 0;
    const body = (await res.json()) as { symbol?: unknown };
    // Guard against a file that belongs to another stock.
    if (body?.symbol !== canonical) return 0;
    return applyLandingSnapshot(client, body);
  } catch {
    return 0;
  }
}

/** The stock symbol in a /stocks/<symbol> path, if it is one. */
export function symbolFromPath(pathname: string): string | null {
  const m = /^\/stocks\/([^/]+)\/?$/.exec(pathname);
  if (!m) return null;
  try {
    return decodeURIComponent(m[1]);
  } catch {
    return null;
  }
}
