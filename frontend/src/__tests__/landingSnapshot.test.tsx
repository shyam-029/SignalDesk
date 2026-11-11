import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  LANDING_SNAPSHOT_MAX_AGE_MS,
  applyLandingSnapshot,
  loadLandingSnapshot,
} from "@/lib/landingSnapshot";
import {
  useAlpha,
  useBenchmarks,
  usePrices,
  useStockDetail,
  useStockList,
  useTechnicals,
} from "@/lib/hooks";

// Mirror of LANDING_QUERIES in backend/app/services/landing_snapshot.py.
const BACKEND_KEYS = [
  ["benchmarks"],
  ["stocks", 1, 50, null, "market_cap", "desc", null],
  ["stocks", 1, 8, null, "market_cap", "desc", null],
  ["stock-detail", "RELIANCE"],
  ["alpha", "RELIANCE"],
  ["technicals", "RELIANCE"],
  ["prices", "RELIANCE", "6mo"],
];

const NOW = Date.parse("2026-11-11T06:00:00Z");
const GEN = "2026-11-10T22:00:00+00:00";

function snap(queries: { key: unknown[]; data: unknown }[], generated_at = GEN) {
  return { version: 1, generated_at, queries };
}

describe("landing snapshot", () => {
  it("uses exactly the query keys the landing hooks build", () => {
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    renderHook(
      () => {
        useBenchmarks();
        useStockList(1, 50, undefined, "market_cap", "desc");
        useStockList(1, 8, undefined, "market_cap", "desc");
        useStockDetail("RELIANCE");
        useAlpha("RELIANCE");
        useTechnicals("RELIANCE");
        usePrices("RELIANCE", "6mo");
      },
      { wrapper },
    );
    const keys = client.getQueryCache().getAll().map((q) => q.queryKey);
    expect(keys).toEqual(BACKEND_KEYS);
  });

  it("seeds empty queries with the snapshot's timestamp", () => {
    const client = new QueryClient();
    const n = applyLandingSnapshot(client, snap([{ key: ["benchmarks"], data: { items: [1] } }]), NOW);
    expect(n).toBe(1);
    expect(client.getQueryData(["benchmarks"])).toEqual({ items: [1] });
    expect(client.getQueryState(["benchmarks"])?.dataUpdatedAt).toBe(Date.parse(GEN));
  });

  it("keeps newer data already in the cache", () => {
    const client = new QueryClient();
    client.setQueryData(["benchmarks"], { items: ["fresh"] }, { updatedAt: NOW });
    applyLandingSnapshot(client, snap([{ key: ["benchmarks"], data: { items: ["old"] } }]), NOW);
    expect(client.getQueryData(["benchmarks"])).toEqual({ items: ["fresh"] });
  });

  it("replaces older cached data", () => {
    const client = new QueryClient();
    client.setQueryData(["benchmarks"], { items: ["older"] }, { updatedAt: Date.parse(GEN) - 1 });
    applyLandingSnapshot(client, snap([{ key: ["benchmarks"], data: { items: ["snap"] } }]), NOW);
    expect(client.getQueryData(["benchmarks"])).toEqual({ items: ["snap"] });
  });

  it("ignores old, malformed or wrong-version snapshots", () => {
    const client = new QueryClient();
    const entry = [{ key: ["benchmarks"], data: {} }];
    const stale = new Date(NOW - LANDING_SNAPSHOT_MAX_AGE_MS - 1).toISOString();
    expect(applyLandingSnapshot(client, snap(entry, stale), NOW)).toBe(0);
    expect(applyLandingSnapshot(client, { ...snap(entry), version: 2 }, NOW)).toBe(0);
    expect(applyLandingSnapshot(client, "<!doctype html>", NOW)).toBe(0);
    expect(applyLandingSnapshot(client, null, NOW)).toBe(0);
    expect(client.getQueryData(["benchmarks"])).toBeUndefined();
  });

  it("does nothing when the file is missing (SPA fallback returns HTML)", async () => {
    const client = new QueryClient();
    const html = vi.fn(async () =>
      new Response("<!doctype html>", { status: 200, headers: { "content-type": "text/html" } }),
    );
    expect(await loadLandingSnapshot(client, html as unknown as typeof fetch)).toBe(0);
    const down = vi.fn(async () => {
      throw new TypeError("offline");
    });
    expect(await loadLandingSnapshot(client, down as unknown as typeof fetch)).toBe(0);
  });
});
