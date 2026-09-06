import { describe, expect, it } from "vitest";

import { filterStocks } from "@/lib/search";
import type { StockSummary } from "@/lib/types";

const stock = (symbol: string, name: string): StockSummary => ({
  symbol,
  name,
  sector: null,
  industry: null,
  last_price: 100,
  change_pct: 0,
  market_cap: null,
});

const CATALOG = [
  stock("RELIANCE.NS", "Reliance Industries"),
  stock("BEL.NS", "Bharat Electronics"),
  stock("TCS.NS", "Tata Consultancy Services"),
  stock("TATAELXSI.NS", "Tata Elxsi"),
  stock("TATAMOTORS.NS", "Tata Motors"),
  stock("INFY.NS", "Infosys"),
];

describe("filterStocks", () => {
  it("matches by ticker prefix with or without the .NS suffix", () => {
    const hits = filterStocks(CATALOG, "bel");
    expect(hits.map((h) => h.symbol)).toEqual(["BEL.NS"]);
    expect(filterStocks(CATALOG, "BEL.NS").map((h) => h.symbol)).toEqual(["BEL.NS"]);
  });

  it("matches by company name substring, case-insensitive", () => {
    const hits = filterStocks(CATALOG, "bharat elec");
    expect(hits.map((h) => h.symbol)).toEqual(["BEL.NS"]);
    expect(filterStocks(CATALOG, "INFOsys").map((h) => h.symbol)).toEqual(["INFY.NS"]);
  });

  it("ranks ticker matches ahead of name matches", () => {
    // "tata" is a ticker prefix (TATAELXSI, TATAMOTORS) and a name substring.
    const hits = filterStocks(CATALOG, "tata");
    expect(hits.map((h) => h.symbol)).toEqual([
      "TATAELXSI.NS",
      "TATAMOTORS.NS",
      "TCS.NS", // name match ("Tata Consultancy...") ranks last
    ]);
  });

  it("breaks ticker ties alphabetically", () => {
    const hits = filterStocks(CATALOG, "tata");
    const tickerHits = hits.slice(0, 2).map((h) => h.symbol);
    expect(tickerHits).toEqual([...tickerHits].sort());
  });

  it("returns nothing for an empty or whitespace query", () => {
    expect(filterStocks(CATALOG, "")).toEqual([]);
    expect(filterStocks(CATALOG, "   ")).toEqual([]);
  });

  it("respects the result limit", () => {
    expect(filterStocks(CATALOG, "a", 2).length).toBeLessThanOrEqual(2);
  });
});
