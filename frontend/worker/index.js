// SignalDesk frontend Worker: serves the built site and keeps the API awake.
//
// fetch:     every request is answered from the static assets (./dist), with
//            the single-page-application fallback set in wrangler.jsonc, so
//            the site behaves exactly as it did when it was assets-only.
// scheduled: Render's free instance sleeps after ~15 minutes without traffic
//            and takes ~40 s to wake. GitHub's scheduled keep-warm workflow
//            was meant to ping every 10 minutes but ran about once every
//            8-14 hours (observed 2026-11-10..12), so visitors kept meeting a
//            sleeping API. Cloudflare Cron Triggers run on time. The cron
//            window lives in wrangler.jsonc (Indian daytime/evening only, to
//            stay inside Render's 750 free instance-hours a month).

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

// /snapshot/stock/<SYMBOL>.json: the stock page's data, built nightly by
// .github/workflows/stock-snapshots.yml into the private R2 bucket bound as
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

  async scheduled(_event, _env, ctx) {
    ctx.waitUntil(
      (async () => {
        await ping("/health", 90_000);
        // Also builds the screener snapshot after a restart or nightly run,
        // so no visitor pays for that build.
        await ping("/api/v1/screener?limit=1", 120_000);
      })(),
    );
  },
};
