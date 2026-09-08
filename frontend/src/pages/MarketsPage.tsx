import * as React from "react";
import { Link } from "react-router-dom";
import {
  ArrowDown,
  ArrowUp,
  Calculator,
  Eye,
  ListPlus,
  Plus,
  Trash2,
  X,
} from "lucide-react";

import { useBenchmarks, useEtfs, useFunds, useMarketNews, useStockList } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { SectionHeader } from "@/components/data/SectionHeader";
import { StockLogo } from "@/components/stock/StockLogo";
import {
  createWatchlist,
  deleteWatchlist,
  removeFromWatchlist,
  useWatchlists,
} from "@/lib/watchlist";
import { useRecentStocks } from "@/lib/recent";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * MarketsPage: the daily dashboard. Index cards up top (Nifty 50, Sensex,
 * India VIX, Nifty Bank, Nifty IT from the stored benchmark tables), then a
 * working grid: today's movers (market-cap bucket filter), the market news
 * feed down the center, device-local recently-viewed and watchlists, ETF and
 * fund snapshots, and the SIP/SWP lab stub.
 */

const BUCKETS = [
  { key: "", label: "All" },
  { key: "large", label: "Large cap" },
  { key: "mid", label: "Mid cap" },
  { key: "small", label: "Small cap" },
] as const;

export default function MarketsPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <SectionHeader index="01" kicker="Dashboard" title="Markets" />
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
        Everything that closes the day in one place: the indexes, today's
        movers within a size class, the market's headlines, and your own
        working list. Prices are daily closes; watchlists and recently viewed
        are stored on this device.
      </p>

      <IndexStrip />

      <div className="mt-8 grid gap-8 lg:grid-cols-12">
        {/* Left column: movers + recently viewed */}
        <div className="space-y-8 lg:col-span-4">
          <MoversPanel />
          <RecentlyViewed />
          <WatchlistPanel />
        </div>

        {/* Center: market news */}
        <div className="lg:col-span-5">
          <MarketNewsPanel />
        </div>

        {/* Right column: ETFs, funds, lab stub */}
        <div className="space-y-8 lg:col-span-3">
          <EtfMiniPanel />
          <FundMiniPanel />
          <LabStub />
        </div>
      </div>
    </div>
  );
}

/* --- Index cards ------------------------------------------------------------ */

function Sparkline({ points, positive }: { points: number[]; positive: boolean }) {
  if (points.length < 2) return <div className="h-9" />;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const w = 120;
  const h = 36;
  const d = points
    .map((v, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((v - min) / span) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-9 w-full" preserveAspectRatio="none" aria-hidden>
      <path d={d} fill="none" stroke={positive ? "var(--band-positive)" : "var(--band-weak)"} strokeWidth="1.5" />
    </svg>
  );
}

function IndexStrip() {
  const query = useBenchmarks();
  const cards = query.data?.items ?? [];
  return (
    <div className="mt-8 grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
      {(cards.length > 0 ? cards : Array.from({ length: 6 }, () => null)).map((c, i) => (
        <div key={c?.symbol ?? i} className="bg-surface p-4">
          {c ? (
            <>
              <p className="label-caps truncate" title={c.name ?? c.symbol}>
                {c.name ?? c.symbol}
              </p>
              <p className="num mt-1 text-lg font-semibold">
                {c.latest_close != null ? c.latest_close.toLocaleString("en-IN", { maximumFractionDigits: 1 }) : "-"}
              </p>
              <p
                className={cn(
                  "num text-xs font-medium",
                  c.change_pct == null ? "text-faint" : c.change_pct >= 0 ? "text-band-positive" : "text-band-weak",
                )}
              >
                {fmtSignedPct(c.change_pct)}
                {c.change_pct != null && (
                  <span className="ml-1 font-normal text-faint">today</span>
                )}
              </p>
              <div className="mt-2">
                <Sparkline points={c.sparkline} positive={(c.change_pct ?? 0) >= 0} />
              </div>
            </>
          ) : (
            <DataState loading={query.isLoading} error={query.error} onRetry={query.refetch} compact>
              <span />
            </DataState>
          )}
        </div>
      ))}
    </div>
  );
}

/* --- Today's movers ---------------------------------------------------------- */

function MoversPanel() {
  const [bucket, setBucket] = React.useState<string>("");
  const [dir, setDir] = React.useState<"desc" | "asc">("desc");
  const query = useStockList(1, 10, undefined, "change_pct", dir, bucket || undefined);
  const items = query.data?.items ?? [];
  const dirLabel = dir === "desc" ? "Top gainers" : "Top losers";

  return (
    <div className="border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-3">
        <p className="label-caps">{dirLabel} · today</p>
        <button
          type="button"
          onClick={() => setDir((d) => (d === "desc" ? "asc" : "desc"))}
          className="label-caps inline-flex items-center gap-1 text-muted transition-colors hover:text-foreground"
        >
          {dir === "desc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />}
          flip
        </button>
      </div>
      <div className="flex flex-wrap gap-1 border-b border-line px-5 py-2">
        {BUCKETS.map((b) => (
          <button
            key={b.key}
            type="button"
            onClick={() => setBucket(b.key)}
            aria-pressed={bucket === b.key}
            className={cn(
              "border px-2 py-0.5 text-xs font-medium transition-colors",
              bucket === b.key
                ? "border-cobalt bg-surface-2 text-foreground"
                : "border-line text-muted hover:text-foreground",
            )}
          >
            {b.label}
          </button>
        ))}
      </div>
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={items.length === 0}
        emptyTitle="No priced stocks in this bucket yet"
        emptyMessage="Ingestion is still filling the universe's daily bars."
        compact
      >
        <ul className="divide-y divide-line">
          {items.map((s) => (
            <li key={s.symbol}>
              <Link
                to={`/stocks/${encodeURIComponent(s.symbol)}`}
                className="flex items-center gap-3 px-5 py-2 transition-colors hover:bg-surface-2/60"
              >
                <StockLogo symbol={s.symbol} name={s.name} size="sm" />
                <span className="min-w-0 flex-1">
                  <span className="num block text-xs font-semibold">{s.symbol.replace(".NS", "")}</span>
                  <span className="block truncate text-xs text-muted">{s.name}</span>
                </span>
                <span className="num text-right text-xs">
                  <span className="block">{fmtPrice(s.last_price)}</span>
                  <span
                    className={cn(
                      "block font-medium",
                      (s.change_pct ?? 0) >= 0 ? "text-band-positive" : "text-band-weak",
                    )}
                  >
                    {fmtSignedPct(s.change_pct)}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </DataState>
    </div>
  );
}

/* --- Recently viewed ---------------------------------------------------------- */

function RecentlyViewed() {
  const recents = useRecentStocks();
  if (recents.length === 0) return null;
  return (
    <div className="border border-line bg-surface">
      <div className="flex items-center gap-2 border-b border-line px-5 py-3">
        <Eye className="size-3.5 text-faint" />
        <p className="label-caps">Recently viewed</p>
        <span className="num ml-auto text-xs text-faint">device-local</span>
      </div>
      <ul className="divide-y divide-line">
        {recents.map((r) => (
          <li key={r.symbol}>
            <Link
              to={`/stocks/${encodeURIComponent(r.symbol)}`}
              className="flex items-center gap-3 px-5 py-2 transition-colors hover:bg-surface-2/60"
            >
              <StockLogo symbol={r.symbol} name={r.name} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="num block text-xs font-semibold">{r.symbol.replace(".NS", "")}</span>
                <span className="block truncate text-xs text-muted">{r.name}</span>
              </span>
              <span className="num text-right text-xs">
                <span className="block">{r.lastPrice != null ? fmtPrice(r.lastPrice) : "-"}</span>
                <span
                  className={cn(
                    "block font-medium",
                    (r.changePct ?? 0) >= 0 ? "text-band-positive" : "text-band-weak",
                  )}
                >
                  {fmtSignedPct(r.changePct)}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* --- Watchlists ---------------------------------------------------------------- */

function WatchlistPanel() {
  const lists = useWatchlists();
  const [creating, setCreating] = React.useState(false);
  const [name, setName] = React.useState("");

  return (
    <div className="border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-5 py-3">
        <p className="label-caps flex items-center gap-2">
          <ListPlus className="size-3.5 text-faint" />
          Watchlists
        </p>
        <button
          type="button"
          onClick={() => setCreating((v) => !v)}
          className="label-caps inline-flex items-center gap-1 text-muted transition-colors hover:text-foreground"
        >
          {creating ? <X className="size-3" /> : <Plus className="size-3" />}
          new
        </button>
      </div>
      {creating && (
        <form
          className="flex gap-2 border-b border-line px-5 py-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) {
              createWatchlist(name);
              setName("");
              setCreating(false);
            }
          }}
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Watchlist name"
            autoFocus
            className="h-8 min-w-0 flex-1 border border-line bg-background px-2 text-sm focus:outline-none"
          />
          <button
            type="submit"
            className="border border-line px-2 text-xs font-medium text-foreground hover:bg-surface-2"
          >
            Create
          </button>
        </form>
      )}
      {lists.length === 0 || lists.every((l) => l.symbols.length === 0) ? (
        <p className="px-5 py-4 text-xs leading-relaxed text-muted">
          No symbols watched yet. Add stocks from any research page (the
          watchlist button in the header) or right here. Watchlists are stored
          on this device; account-backed lists arrive with the workspace.
        </p>
      ) : (
        <div className="divide-y divide-line">
          {lists
            .filter((l) => l.symbols.length > 0)
            .map((l) => (
              <div key={l.id} className="px-5 py-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold">{l.name}</p>
                  {l.id !== "default" && (
                    <button
                      type="button"
                      aria-label={`Delete ${l.name}`}
                      onClick={() => deleteWatchlist(l.id)}
                      className="text-faint transition-colors hover:text-band-weak"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  )}
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {l.symbols.map((sym) => (
                    <span
                      key={sym}
                      className="group inline-flex items-center gap-1 border border-line bg-surface-2 px-1.5 py-0.5 text-xs"
                    >
                      <Link to={`/stocks/${encodeURIComponent(sym)}`} className="num hover:underline">
                        {sym.replace(".NS", "")}
                      </Link>
                      <button
                        type="button"
                        aria-label={`Remove ${sym}`}
                        onClick={() => removeFromWatchlist(l.id, sym)}
                        className="text-faint hover:text-band-weak"
                      >
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

/* --- Market news ---------------------------------------------------------------- */

function MarketNewsPanel() {
  const query = useMarketNews(18);
  const items = query.data?.items ?? [];
  return (
    <div className="border border-line bg-surface">
      <div className="flex items-baseline justify-between border-b border-line px-5 py-3">
        <p className="label-caps">Market news · latest across the universe</p>
        <p className="num text-xs text-faint">{query.data ? `${items.length} articles` : ""}</p>
      </div>
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={items.length === 0}
        emptyTitle="No articles yet"
        emptyMessage="News ingestion has not filled today's feed yet."
        compact
      >
        <ul className="max-h-[520px] divide-y divide-line overflow-y-auto">
          {items.map((a) => (
            <li key={a.id} className="px-5 py-2.5">
              <a
                href={a.url}
                target="_blank"
                rel="noreferrer"
                className="group block"
              >
                <p className="text-sm leading-snug group-hover:underline">{a.title}</p>
                <p className="num mt-0.5 flex flex-wrap items-center gap-2 text-xs text-faint">
                  <span className="font-semibold text-muted">{a.symbol.replace(".NS", "")}</span>
                  <span>{a.source}</span>
                  {a.published_at && <span>{new Date(a.published_at).toLocaleDateString("en-IN")}</span>}
                  {a.sentiment && <span className="capitalize">{a.sentiment}</span>}
                </p>
              </a>
            </li>
          ))}
        </ul>
      </DataState>
    </div>
  );
}

/* --- ETF + fund snapshots --------------------------------------------------------- */

function EtfMiniPanel() {
  const query = useEtfs();
  const items = (query.data?.items ?? [])
    .filter((e) => e.change_pct != null)
    .sort((a, b) => Math.abs(b.change_pct ?? 0) - Math.abs(a.change_pct ?? 0))
    .slice(0, 6);
  return (
    <div className="border border-line bg-surface">
      <div className="flex items-baseline justify-between border-b border-line px-5 py-3">
        <p className="label-caps">ETFs · biggest moves</p>
        <Link to="/etfs" className="text-xs text-cobalt hover:underline dark:text-cobalt-strong">
          all
        </Link>
      </div>
      <ul className="divide-y divide-line">
        {items.map((e) => (
          <li key={e.symbol}>
            <Link
              to={`/stocks/${encodeURIComponent(e.symbol)}`}
              className="flex items-center justify-between gap-2 px-5 py-2 transition-colors hover:bg-surface-2/60"
            >
              <span className="num truncate text-xs font-semibold">{e.symbol.replace(".NS", "")}</span>
              <span className="num flex items-baseline gap-2 text-xs">
                {fmtPrice(e.last_price)}
                <span className={cn("font-medium", (e.change_pct ?? 0) >= 0 ? "text-band-positive" : "text-band-weak")}>
                  {fmtSignedPct(e.change_pct)}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FundMiniPanel() {
  const query = useFunds("return_1m", "desc");
  const items = (query.data?.items ?? []).slice(0, 6);
  return (
    <div className="border border-line bg-surface">
      <div className="flex items-baseline justify-between border-b border-line px-5 py-3">
        <p className="label-caps">Funds · best 1M</p>
        <Link to="/funds" className="text-xs text-cobalt hover:underline dark:text-cobalt-strong">
          all
        </Link>
      </div>
      <ul className="divide-y divide-line">
        {items.map((f) => (
          <li key={f.id}>
            <Link
              to={`/funds/${f.id}`}
              className="flex items-center justify-between gap-2 px-5 py-2 transition-colors hover:bg-surface-2/60"
            >
              <span className="min-w-0">
                <span className="block truncate text-xs font-semibold">{f.name}</span>
                <span className="block text-xs text-faint">{f.category ?? "-"}</span>
              </span>
              <span
                className={cn(
                  "num text-xs font-medium",
                  (f.return_1m_pct ?? 0) >= 0 ? "text-band-positive" : "text-band-weak",
                )}
              >
                {fmtSignedPct(f.return_1m_pct)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* --- SIP/SWP lab stub --------------------------------------------------------------- */

function LabStub() {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="border border-dashed border-line p-5">
      <p className="label-caps flex items-center gap-2">
        <Calculator className="size-3.5 text-faint" />
        SIP / SWP lab
      </p>
      <p className="mt-2 text-xs leading-relaxed text-muted">
        Goal-based SIP and withdrawal simulators over historical NAV
        distributions. Planned for the scenario lab.
      </p>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mt-3 border border-line px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-surface-2"
      >
        {open ? "Close" : "Preview"}
      </button>
      {open && (
        <p className="mt-2 border border-line bg-surface-2 px-3 py-2 text-xs leading-relaxed text-muted">
          Coming soon. The simulator is scoped for the scenario and forecast
          lab: historical bootstrap of SIP/SWP outcomes with explicit
          uncertainty, never a promised return.
        </p>
      )}
    </div>
  );
}
