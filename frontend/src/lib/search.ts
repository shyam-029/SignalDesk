// Stock catalog search: match by ticker OR company name.
//
// Pure function (unit-tested) so the header component only wires input state
// to navigation. Ranking: symbol-prefix matches first, then symbol
// substrings, then name-prefix, then name substrings; ties break
// alphabetically. Everything is case-insensitive and the ".NS" suffix is
// optional when typing a ticker ("reliance" and "reliance.ns" both match).

import type { StockSummary } from "./types";

export interface SearchHit {
  symbol: string;
  name: string;
}

export function filterStocks(
  items: StockSummary[],
  rawQuery: string,
  limit = 8,
): SearchHit[] {
  const q = rawQuery.trim().toLowerCase();
  if (!q) return [];
  const bare = q.replace(/\.ns$/, "");

  const scored: Array<{ hit: SearchHit; rank: number }> = [];
  for (const s of items) {
    const symbol = s.symbol.toLowerCase();
    const bareSymbol = symbol.replace(/\.ns$/, "");
    const name = (s.name ?? "").toLowerCase();

    let rank: number | null = null;
    if (bareSymbol.startsWith(bare) || symbol.startsWith(q)) rank = 0;
    else if (bare && symbol.includes(bare)) rank = 1;
    else if (name.startsWith(q)) rank = 2;
    else if (name.includes(q)) rank = 3;

    if (rank != null) {
      scored.push({ hit: { symbol: s.symbol, name: s.name }, rank });
    }
  }

  scored.sort(
    (a, b) => a.rank - b.rank || a.hit.symbol.localeCompare(b.hit.symbol),
  );
  return scored.slice(0, limit).map((s) => s.hit);
}
