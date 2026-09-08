// Watchlists: device-local (localStorage), multiple named lists.
//
// Account-backed watchlists arrive with M3 (auth). Until then this store
// keeps the feature honest: real, persistent on this device, labeled
// "device-local" in the UI. useSyncExternalStore keeps every panel in sync.

import { useSyncExternalStore } from "react";

export interface Watchlist {
  id: string;
  name: string;
  symbols: string[];
}

const KEY = "sd_watchlists_v1";
const DEFAULT_ID = "default";

let cache: Watchlist[] | null = null;
const listeners = new Set<() => void>();

function read(): Watchlist[] {
  if (cache) return cache;
  try {
    const raw = localStorage.getItem(KEY);
    cache = raw ? (JSON.parse(raw) as Watchlist[]) : [];
  } catch {
    cache = [];
  }
  if (!cache.some((l) => l.id === DEFAULT_ID)) {
    cache = [{ id: DEFAULT_ID, name: "My watchlist", symbols: [] }, ...cache];
  }
  return cache;
}

function write(next: Watchlist[]): void {
  cache = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Storage full/blocked: the in-memory copy still works for the session.
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function createWatchlist(name: string): Watchlist {
  const trimmed = name.trim() || "Untitled";
  const list: Watchlist = {
    id: `wl_${Date.now().toString(36)}`,
    name: trimmed,
    symbols: [],
  };
  write([...read(), list]);
  return list;
}

export function deleteWatchlist(id: string): void {
  if (id === DEFAULT_ID) return; // the default list stays
  write(read().filter((l) => l.id !== id));
}

export function addToWatchlist(id: string, symbol: string): void {
  write(
    read().map((l) =>
      l.id === id && !l.symbols.includes(symbol)
        ? { ...l, symbols: [...l.symbols, symbol] }
        : l,
    ),
  );
}

export function removeFromWatchlist(id: string, symbol: string): void {
  write(
    read().map((l) =>
      l.id === id ? { ...l, symbols: l.symbols.filter((s) => s !== symbol) } : l,
    ),
  );
}

export function isWatched(id: string, symbol: string): boolean {
  return read().some((l) => l.id === id && l.symbols.includes(symbol));
}

export function useWatchlists(): Watchlist[] {
  return useSyncExternalStore(subscribe, read, read);
}

export { DEFAULT_ID as DEFAULT_WATCHLIST_ID };
