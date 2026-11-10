// Persist the TanStack Query cache in the browser (work list item 16).
//
// A repeat visit renders the last-seen data immediately from localStorage,
// then refetches in the background as usual (restored queries keep their
// original timestamps, so anything older than its staleTime is refreshed).
// This hides the API's cold start for returning visitors.
//
// Uses only dehydrate/hydrate from @tanstack/react-query (no extra package).
// Storage can be missing, full or blocked (private mode): every access is
// guarded and the app works exactly as before without it.

import { dehydrate, hydrate, type QueryClient } from "@tanstack/react-query";

const STORAGE_KEY = "signaldesk:query-cache";
// Bump when API response shapes change so old snapshots are discarded.
export const CACHE_VERSION = "1";
// Older snapshots are ignored: the data changes nightly.
export const PERSIST_MAX_AGE_MS = 12 * 60 * 60 * 1000;
// Stay well inside the ~5 MB localStorage quota shared with the rest of the app.
export const PERSIST_MAX_CHARS = 1_500_000;
const WRITE_DEBOUNCE_MS = 1000;

export type KeyValueStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

type Snapshot = { version: string; savedAt: number; state: unknown };

function browserStorage(): KeyValueStorage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** Load a saved snapshot into the client. Returns true when one was restored. */
export function restoreQueryCache(
  client: QueryClient,
  storage: KeyValueStorage | null = browserStorage(),
  now: number = Date.now(),
): boolean {
  if (!storage) return false;
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const snap = JSON.parse(raw) as Snapshot;
    if (snap.version !== CACHE_VERSION || now - snap.savedAt > PERSIST_MAX_AGE_MS) {
      storage.removeItem(STORAGE_KEY);
      return false;
    }
    hydrate(client, snap.state as Parameters<typeof hydrate>[1]);
    return true;
  } catch {
    try {
      storage.removeItem(STORAGE_KEY);
    } catch {
      /* storage unusable: nothing to clean */
    }
    return false;
  }
}

/** Write the current successful queries to storage. Returns true on success. */
export function saveQueryCache(
  client: QueryClient,
  storage: KeyValueStorage | null = browserStorage(),
  now: number = Date.now(),
): boolean {
  if (!storage) return false;
  try {
    const state = dehydrate(client, {
      shouldDehydrateQuery: (q) => q.state.status === "success",
    });
    const raw = JSON.stringify({ version: CACHE_VERSION, savedAt: now, state } satisfies Snapshot);
    if (raw.length > PERSIST_MAX_CHARS) return false; // too big: skip, never truncate
    storage.setItem(STORAGE_KEY, raw);
    return true;
  } catch {
    return false; // quota exceeded or storage blocked
  }
}

/** Restore once, then save (debounced) whenever the cache changes. */
export function persistQueryCache(
  client: QueryClient,
  storage: KeyValueStorage | null = browserStorage(),
): () => void {
  restoreQueryCache(client, storage);
  if (!storage) return () => {};
  let timer: ReturnType<typeof setTimeout> | undefined;
  const unsubscribe = client.getQueryCache().subscribe((event) => {
    if (event.type !== "updated" && event.type !== "removed") return;
    clearTimeout(timer);
    timer = setTimeout(() => saveQueryCache(client, storage), WRITE_DEBOUNCE_MS);
  });
  return () => {
    clearTimeout(timer);
    unsubscribe();
  };
}
