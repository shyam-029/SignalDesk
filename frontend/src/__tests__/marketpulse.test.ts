import { describe, expect, it } from "vitest";

import { orderBenchmarks } from "@/components/landing/MarketPulse";
import type { BenchmarkCard } from "@/lib/types";

function card(symbol: string, changePct: number | null = 0.5): BenchmarkCard {
  return {
    symbol,
    name: symbol,
    latest_close: 100,
    change_pct: changePct,
    as_of: "2026-09-09",
    sparkline: [99, 100],
  };
}

describe("orderBenchmarks", () => {
  it("orders the tape: headline indexes, macro, then sectors/breadth", () => {
    const shuffled = [
      card("^CNXIT"),
      card("GC=F"),
      card("^NSEI"),
      card("^NSEBANK"),
      card("INR=X"),
      card("^BSESN"),
    ];
    expect(orderBenchmarks(shuffled).map((b) => b.symbol)).toEqual([
      "^NSEI", "^BSESN", "INR=X", "GC=F", "^NSEBANK", "^CNXIT",
    ]);
  });

  it("appends benchmarks outside the known order at the end", () => {
    const extra = card("^MYSTERY");
    const ordered = orderBenchmarks([extra, card("^NSEI")]);
    expect(ordered.map((b) => b.symbol)).toEqual(["^NSEI", "^MYSTERY"]);
  });

  it("skips benchmarks missing from the stored set", () => {
    const ordered = orderBenchmarks([card("^NSEI"), card("^CNXIT")]);
    expect(ordered.map((b) => b.symbol)).toEqual(["^NSEI", "^CNXIT"]);
  });

  it("passes the real change values through untouched", () => {
    const [nifty] = orderBenchmarks([card("^NSEI", -0.61)]);
    expect(nifty.change_pct).toBe(-0.61);
  });
});
