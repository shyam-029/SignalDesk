import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  loadStockSnapshot,
  resetStockSnapshots,
  stockSnapshotUrl,
  symbolFromPath,
} from "@/lib/stockSnapshot";
import {
  useAlpha,
  useAltman,
  useCompanyProfile,
  useFinancialsHistory,
  useFundamentals,
  useNews,
  usePeers,
  usePerformance,
  usePrices,
  useScores,
  useSentiment,
  useStockDetail,
  useStrength,
  useTechnicals,
  useValuation,
} from "@/lib/hooks";

// Mirror of stock_queries() in backend/app/services/stock_snapshot.py.
const S = "RELIANCE";
const BACKEND_KEYS = [
  ["stock-detail", S],
  ["performance", S],
  ["alpha", S],
  ["company-profile", S],
  ["prices", S, "6mo"],
  ["technicals", S],
  ["valuation", S, "PE"],
  ["valuation", S, "EV_EBITDA"],
  ["valuation", S, "PB"],
  ["valuation", S, "PS"],
  ["fundamentals", S],
  ["scores", S],
  ["altman", S],
  ["financials-history", S, "quarterly"],
  ["peers", S],
  ["news", S, 12],
  ["sentiment", S],
  ["strength", S],
];

function jsonResponse(body: unknown, ok = true) {
  return {
    ok,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => body,
  } as unknown as Response;
}

const recent = () => new Date(Date.now() - 60_000).toISOString();

afterEach(() => resetStockSnapshots());

describe("stock snapshot", () => {
  it("uses exactly the query keys the stock page's hooks build (default tabs)", () => {
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    renderHook(
      () => {
        useStockDetail(S);
        usePerformance(S);
        useAlpha(S);
        useCompanyProfile(S);
        usePrices(S, "6mo");
        useTechnicals(S);
        useValuation(S, "PE");
        useValuation(S, "EV_EBITDA");
        useValuation(S, "PB");
        useValuation(S, "PS");
        useFundamentals(S);
        useScores(S);
        useAltman(S);
        useFinancialsHistory(S);
        usePeers(S);
        useNews(S, 12);
        useSentiment(S);
        useStrength(S);
      },
      { wrapper },
    );
    const keys = client.getQueryCache().getAll().map((q) => q.queryKey);
    expect(keys).toEqual(BACKEND_KEYS);
  });

  it("fetches the canonical symbol's file and seeds the cache", async () => {
    const client = new QueryClient();
    const fetchImpl = vi.fn(async () =>
      jsonResponse({
        version: 1,
        generated_at: recent(),
        symbol: "M&M",
        queries: [{ key: ["stock-detail", "M&M"], data: { name: "Mahindra" } }],
      }),
    );
    const n = await loadStockSnapshot(client, "m&m.ns", fetchImpl as unknown as typeof fetch);
    expect(fetchImpl).toHaveBeenCalledWith("/snapshot/stock/M%26M.json");
    expect(n).toBe(1);
    expect(client.getQueryData(["stock-detail", "M&M"])).toEqual({ name: "Mahindra" });
  });

  it("fetches each symbol once per visit", async () => {
    const client = new QueryClient();
    const fetchImpl = vi.fn(async () => jsonResponse({}, false));
    await loadStockSnapshot(client, "TCS", fetchImpl as unknown as typeof fetch);
    await loadStockSnapshot(client, "TCS.NS", fetchImpl as unknown as typeof fetch);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("ignores a file for another stock, a missing file and network errors", async () => {
    const client = new QueryClient();
    const other = vi.fn(async () =>
      jsonResponse({
        version: 1,
        generated_at: recent(),
        symbol: "TCS",
        queries: [{ key: ["stock-detail", "TCS"], data: {} }],
      }),
    );
    expect(await loadStockSnapshot(client, "INFY", other as unknown as typeof fetch)).toBe(0);
    const missing = vi.fn(async () => jsonResponse({}, false));
    expect(await loadStockSnapshot(client, "WIPRO", missing as unknown as typeof fetch)).toBe(0);
    const broken = vi.fn(async () => {
      throw new Error("offline");
    });
    expect(await loadStockSnapshot(client, "HCLTECH", broken as unknown as typeof fetch)).toBe(0);
    expect(client.getQueryCache().getAll()).toHaveLength(0);
  });

  it("reads the symbol from stock URLs only", () => {
    expect(symbolFromPath("/stocks/RELIANCE.NS")).toBe("RELIANCE.NS");
    expect(symbolFromPath("/stocks/M%26M")).toBe("M&M");
    expect(symbolFromPath("/markets")).toBeNull();
    expect(symbolFromPath("/stocks/A/b")).toBeNull();
    expect(stockSnapshotUrl("tcs.ns")).toBe("/snapshot/stock/TCS.json");
  });
});
