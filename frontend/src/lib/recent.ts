// Recently viewed stocks: device-local (localStorage), newest first, max 8.
//
// Every stock-page visit records the symbol, name and the day's price
// snapshot so the markets dashboard can render "pick up where you left off"
// without any backend state.

import { useSyncExternalStore } from "react";

export interface RecentStock {
  symbol: string;
  name: string;
  lastPrice: number | null;
  changePct: number | null;
  ts: number;
}

const KEY = "sd_recent_v1";
const MAX = 8;

let cache: RecentStock[] | null = null;
const listeners = new Set<() => void>();

function read(): RecentStock[] {
  if (cache) return cache;
  try {
    const raw = localStorage.getItem(KEY);
    cache = raw ? (JSON.parse(raw) as RecentStock[]) : [];
  } catch {
    cache = [];
  }
  return cache;
}

function write(next: RecentStock[]): void {
  cache = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Ignore storage failures: session memory still serves.
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function recordRecent(
  symbol: string,
  name: string,
  lastPrice: number | null,
  changePct: number | null,
): void {
  const rest = read().filter((r) => r.symbol !== symbol);
  write([{ symbol, name, lastPrice, changePct, ts: Date.now() }, ...rest].slice(0, MAX));
}

export function clearRecent(): void {
  write([]);
}

export function useRecentStocks(): RecentStock[] {
  return useSyncExternalStore(subscribe, read, read);
}
