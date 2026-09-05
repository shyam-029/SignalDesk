import { describe, expect, it } from "vitest";

import { pickTopMovers } from "@/components/landing/MarketPulse";
import type { StockSummary } from "@/lib/types";

function stock(symbol: string, changePct: number, lastPrice = 100): StockSummary {
  return { symbol, name: symbol, sector: null, industry: null, market_cap: null, last_price: lastPrice, change_pct: changePct };
}

describe("pickTopMovers", () => {
  it("ranks by absolute daily move, not by sign", () => {
    const movers = pickTopMovers([
      stock("A.NS", 0.4),
      stock("B.NS", -2.1),
      stock("C.NS", 1.2),
      stock("D.NS", 5.8),
      stock("E.NS", -3.3),
    ]);
    expect(movers.map((m) => m.symbol)).toEqual(["D.NS", "E.NS", "B.NS", "C.NS", "A.NS"]);
  });

  it("caps the strip at the requested count", () => {
    const items = Array.from({ length: 30 }, (_, i) => stock(`S${i}.NS`, (i % 7) - 3));
    expect(pickTopMovers(items, 7)).toHaveLength(7);
    expect(pickTopMovers(items)).toHaveLength(7);
  });

  it("keeps the real price and change values untouched", () => {
    const movers = pickTopMovers([stock("RELIANCE.NS", -1.05, 1322)]);
    expect(movers[0]).toEqual({
      symbol: "RELIANCE.NS",
      name: "RELIANCE.NS",
      lastPrice: 1322,
      changePct: -1.05,
    });
  });

  it("drops non-finite changes instead of guessing", () => {
    const broken = {
      symbol: "X.NS",
      name: "X",
      sector: null, industry: null, market_cap: null,
      last_price: 10,
      change_pct: Number.NaN,
    };
    const movers = pickTopMovers([broken, stock("OK.NS", 0.9)]);
    expect(movers).toHaveLength(1);
    expect(movers[0].symbol).toBe("OK.NS");
  });

  it("returns an empty list for an empty catalog", () => {
    expect(pickTopMovers([])).toEqual([]);
  });
});

