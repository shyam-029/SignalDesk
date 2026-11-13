// SignalDesk frontend Worker: serves the built site and keeps the API awake.
//
// fetch:     every request is answered from the static assets (./dist), with
//            the single-page-application fallback set in wrangler.jsonc, so
//            the site behaves exactly as it did when it was assets-only.
// scheduled: Render's free instance sleeps after ~15 minutes without traffic
//            and takes ~40 s to wake. GitHub's scheduled keep-warm workflow
//            was meant to ping every 10 minutes but ran about once every
//            8-14 hours (observed 2026-11-10..12), so visitors kept meeting a
//            sleeping API. Cloudflare Cron Triggers run on time, so that
//            workflow was removed on 2026-11-13 and this is the only pinger. The cron
//            window lives in wrangler.jsonc (Indian daytime/evening only, to
//            stay inside Render's 750 free instance-hours a month).
//            Two more crons start the nightly ingest (see ensureNightly).

const API = "https://signaldesk-31gt.onrender.com";

async function ping(path, timeoutMs) {
  const started = Date.now();
  try {
    const res = await fetch(API + path, {
      signal: AbortSignal.timeout(timeoutMs),
      headers: { "user-agent": "signaldesk-keep-warm" },
    });
    console.log(`${path} ${res.status} in ${Date.now() - started} ms`);
  } catch (err) {
    // A missed ping is not an incident; the next one runs in 10 minutes.
    console.log(`${path} failed after ${Date.now() - started} ms: ${err}`);
  }
}

// --- Nightly ingest trigger ---------------------------------------------------
// GitHub's own schedule started the 16:15 IST nightly up to 8 hours late
// (2026-11-12: due 10:45 UTC, began 18:36 UTC). These crons ask GitHub to run
// ingest.yml now (workflow_dispatch), which starts within seconds:
//   NIGHTLY_CRON  10:45 UTC = 16:15 IST, the nightly's slot
//   RETRY_CRON    12:45 UTC = 18:15 IST, starts it again only if today's run
//                 failed or never started (e.g. the 2026-11-11 run whose
//                 GitHub machine died)
// Both first check today's runs, so a run already going or done (including
// one started by hand) is never duplicated. GITHUB_DISPATCH_TOKEN is a Worker
// secret: a fine-grained GitHub token limited to this repository with
// "Actions: read and write". Without it nothing is dispatched and the
// watchdog workflow alerts after 30 h with no successful ingest.
/** True on the two keep-warm ticks a day that also warm the screener (03:00 and 13:00 UTC). */
export function shouldWarmScreener(scheduledTime) {
  const t = new Date(scheduledTime ?? Date.now());
  return t.getUTCMinutes() < 10 && (t.getUTCHours() === 3 || t.getUTCHours() === 13);
}

export const NIGHTLY_CRON = "45 10 * * *";
export const RETRY_CRON = "45 12 * * *";
const REPO = "shyam-029/SignalDesk";
const WORKFLOW = "ingest.yml";
const ACTIVE = new Set(["queued", "in_progress", "waiting", "requested", "pending"]);

function github(env, path, init = {}) {
  return fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...init,
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
      "user-agent": "signaldesk-nightly-trigger",
      "x-github-api-version": "2022-11-28",
      ...(init.body ? { "content-type": "application/json" } : {}),
    },
    signal: AbortSignal.timeout(20_000),
  });
}

/** Start today's ingest unless one is running or has succeeded. Returns what it did. */
export async function ensureNightly(env, now = new Date()) {
  if (!env.GITHUB_DISPATCH_TOKEN) {
    console.log("nightly: GITHUB_DISPATCH_TOKEN is not set; nothing dispatched");
    return "no-token";
  }
  const today = now.toISOString().slice(0, 10);
  const res = await github(
    env,
    `/actions/workflows/${WORKFLOW}/runs?created=${encodeURIComponent(">=" + today)}&per_page=30`,
  );
  if (!res.ok) {
    console.log(`nightly: could not list today's runs (HTTP ${res.status}); nothing dispatched`);
    return "list-failed";
  }
  const runs = (await res.json()).workflow_runs ?? [];
  const busy = runs.find((r) => ACTIVE.has(r.status));
  if (busy) {
    console.log(`nightly: run ${busy.id} is ${busy.status}; not starting another`);
    return "running";
  }
  const done = runs.find((r) => r.conclusion === "success");
  if (done) {
    console.log(`nightly: run ${done.id} already succeeded today`);
    return "done";
  }
  const d = await github(env, `/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: "main" }),
  });
  console.log(`nightly: dispatch ${WORKFLOW} -> HTTP ${d.status} (${runs.length} earlier run(s) today)`);
  return d.status === 204 ? "dispatched" : "dispatch-failed";
}

// /snapshot/stock/<SYMBOL>.json: the stock page's data, built nightly by
// .github/workflows/ingest.yml (stock-snapshots job) into the private R2 bucket bound as
// SNAPSHOTS. Only this exact shape is served, so no other object in the
// bucket can be reached. Static assets (including /snapshot/landing.json)
// are matched before this script runs.
const STOCK_SNAPSHOT = /^\/snapshot\/stock\/([^/]+)\.json$/;
const SYMBOL = /^[A-Z0-9&_-][A-Z0-9&._-]{0,39}$/;

function notFound() {
  return new Response("Not found", {
    status: 404,
    headers: { "content-type": "text/plain", "cache-control": "public, max-age=60" },
  });
}

async function stockSnapshot(request, env, match) {
  let symbol;
  try {
    symbol = decodeURIComponent(match[1]);
  } catch {
    return notFound();
  }
  if (!SYMBOL.test(symbol) || symbol.includes("..") || !env.SNAPSHOTS) return notFound();
  const obj = await env.SNAPSHOTS.get(`stock/${symbol}.json`);
  if (!obj) return notFound();
  const headers = new Headers({
    "content-type": "application/json",
    "cache-control": "public, max-age=300",
    etag: obj.httpEtag,
  });
  if (request.headers.get("if-none-match") === obj.httpEtag) {
    return new Response(null, { status: 304, headers });
  }
  return new Response(obj.body, { headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const match = request.method === "GET" ? STOCK_SNAPSHOT.exec(url.pathname) : null;
    if (match) return stockSnapshot(request, env, match);
    return env.ASSETS.fetch(request);
  },

  async scheduled(event, env, ctx) {
    if (event.cron === NIGHTLY_CRON || event.cron === RETRY_CRON) {
      ctx.waitUntil(
        ensureNightly(env).catch((err) => console.log(`nightly: error ${err}`)),
      );
      return;
    }
    ctx.waitUntil(
      (async () => {
        // /health never touches the database: it keeps Render awake while
        // Neon is free to suspend (after 5 idle minutes) between real visits.
        // Until 2026-11-13 every ping also asked for a screener row, which
        // queries the database, so a ping every 10 minutes kept Neon's
        // compute awake about half of the 17-hour window, roughly 2 of the
        // free plan's 100 CU-hours a day.
        await ping("/health", 90_000);
        // The screener snapshot (built from the database) is warmed only
        // twice a day: 08:30 IST, the first visits of the day, and
        // 18:30 IST, after the nightly has finished.
        if (shouldWarmScreener(event.scheduledTime)) {
          await ping("/api/v1/screener?limit=1", 120_000);
        }
      })(),
    );
  },
};
