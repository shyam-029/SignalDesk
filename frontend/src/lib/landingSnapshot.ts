// Landing-page snapshot (work list item 13).
//
// The nightly workflow (.github/workflows/ingest.yml, landing-snapshot job) commits
// public/snapshot/landing.json: the landing page's API responses, each under
// the TanStack Query key its hook uses. Cloudflare serves it as a static
// file, so it arrives in milliseconds even while the Render API is still
// waking up. We put each response into the query cache with the snapshot's
// own timestamp: the page renders it at once, and the hooks still refetch
// from the API in the background (the data is older than their staleTime).
//
// Data already in the cache (for example restored from localStorage) wins
// when it is newer. A missing, malformed or very old file changes nothing.

import type { QueryClient, QueryKey } from "@tanstack/react-query";

export const LANDING_SNAPSHOT_URL = "/snapshot/landing.json";
export const LANDING_SNAPSHOT_VERSION = 1;
// Past this the file is ignored (the nightly normally refreshes it daily).
export const LANDING_SNAPSHOT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

type Entry = { key: QueryKey; data: unknown };
export type LandingSnapshot = { version: number; generated_at: string; queries: Entry[] };

function isSnapshot(x: unknown): x is LandingSnapshot {
  const s = x as LandingSnapshot;
  return (
    !!s &&
    s.version === LANDING_SNAPSHOT_VERSION &&
    typeof s.generated_at === "string" &&
    Array.isArray(s.queries)
  );
}

/** Seed the cache from a parsed snapshot. Returns how many queries were seeded. */
export function applyLandingSnapshot(
  client: QueryClient,
  snapshot: unknown,
  now: number = Date.now(),
): number {
  if (!isSnapshot(snapshot)) return 0;
  const at = Date.parse(snapshot.generated_at);
  if (!Number.isFinite(at) || now - at > LANDING_SNAPSHOT_MAX_AGE_MS) return 0;
  let seeded = 0;
  for (const q of snapshot.queries) {
    if (!Array.isArray(q?.key) || q.data == null) continue;
    const existing = client.getQueryState(q.key);
    if (existing?.data !== undefined && existing.dataUpdatedAt >= at) continue;
    client.setQueryData(q.key, q.data, { updatedAt: at });
    seeded++;
  }
  return seeded;
}

/** Fetch the static snapshot and seed the cache. Never throws. */
export async function loadLandingSnapshot(
  client: QueryClient,
  fetchImpl: typeof fetch = fetch,
): Promise<number> {
  try {
    const res = await fetchImpl(LANDING_SNAPSHOT_URL);
    // Unknown paths fall back to index.html (SPA routing), so check the type.
    if (!res.ok || !(res.headers.get("content-type") ?? "").includes("json")) return 0;
    return applyLandingSnapshot(client, await res.json());
  } catch {
    return 0;
  }
}
