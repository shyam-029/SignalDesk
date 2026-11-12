// Broad market first, then sectors, then size and breadth, volatility last.
// The API lists benchmarks alphabetically by Yahoo symbol, which put SENSEX
// first and NIFTY 50 seventh. Unknown symbols keep their order at the end.
export const INDEX_ORDER = [
  "^NSEI",
  "^BSESN",
  "^NSEBANK",
  "^CNXIT",
  "^CNXPHARMA",
  "^NSEMDCP50",
  "^CRSLDX",
  "^INDIAVIX",
];

export function orderIndexes<T extends { symbol: string }>(items: T[]): T[] {
  const rank = (s: string) => {
    const i = INDEX_ORDER.indexOf(s);
    return i === -1 ? INDEX_ORDER.length : i;
  };
  return [...items].sort((a, b) => rank(a.symbol) - rank(b.symbol));
}
