import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import {
  CACHE_VERSION,
  PERSIST_MAX_AGE_MS,
  PERSIST_MAX_CHARS,
  restoreQueryCache,
  saveQueryCache,
  type KeyValueStorage,
} from "@/lib/queryPersist";

function memoryStorage(): KeyValueStorage & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

const NOW = 1_800_000_000_000;

describe("query cache persistence", () => {
  it("round-trips successful queries into a fresh client", () => {
    const storage = memoryStorage();
    const a = new QueryClient();
    a.setQueryData(["stocks"], [{ symbol: "RELIANCE.NS" }]);
    expect(saveQueryCache(a, storage, NOW)).toBe(true);

    const b = new QueryClient();
    expect(restoreQueryCache(b, storage, NOW + 1000)).toBe(true);
    expect(b.getQueryData(["stocks"])).toEqual([{ symbol: "RELIANCE.NS" }]);
  });

  it("does not persist failed queries", () => {
    const storage = memoryStorage();
    const a = new QueryClient();
    a.getQueryCache().build(a, { queryKey: ["broken"] }).setState({
      status: "error",
      error: new Error("x"),
    });
    a.setQueryData(["ok"], 1);
    saveQueryCache(a, storage, NOW);

    const b = new QueryClient();
    restoreQueryCache(b, storage, NOW);
    expect(b.getQueryData(["ok"])).toBe(1);
    expect(b.getQueryCache().find({ queryKey: ["broken"] })).toBeUndefined();
  });

  it("ignores and removes snapshots that are too old", () => {
    const storage = memoryStorage();
    const a = new QueryClient();
    a.setQueryData(["stocks"], [1]);
    saveQueryCache(a, storage, NOW);

    const b = new QueryClient();
    expect(restoreQueryCache(b, storage, NOW + PERSIST_MAX_AGE_MS + 1)).toBe(false);
    expect(b.getQueryData(["stocks"])).toBeUndefined();
    expect(storage.data.size).toBe(0);
  });

  it("ignores snapshots from another cache version", () => {
    const storage = memoryStorage();
    storage.setItem(
      "signaldesk:query-cache",
      JSON.stringify({ version: `${CACHE_VERSION}-old`, savedAt: NOW, state: { queries: [] } }),
    );
    expect(restoreQueryCache(new QueryClient(), storage, NOW)).toBe(false);
    expect(storage.data.size).toBe(0);
  });

  it("survives corrupt, blocked or missing storage", () => {
    const storage = memoryStorage();
    storage.setItem("signaldesk:query-cache", "{not json");
    expect(restoreQueryCache(new QueryClient(), storage, NOW)).toBe(false);

    const blocked: KeyValueStorage = {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
      removeItem: () => {
        throw new Error("SecurityError");
      },
    };
    const client = new QueryClient();
    client.setQueryData(["x"], 1);
    expect(restoreQueryCache(client, blocked, NOW)).toBe(false);
    expect(saveQueryCache(client, blocked, NOW)).toBe(false);
    expect(restoreQueryCache(client, null, NOW)).toBe(false);
  });

  it("skips writing a snapshot larger than the size cap", () => {
    const storage = memoryStorage();
    const a = new QueryClient();
    a.setQueryData(["big"], "x".repeat(PERSIST_MAX_CHARS));
    expect(saveQueryCache(a, storage, NOW)).toBe(false);
    expect(storage.data.size).toBe(0);
  });
});
