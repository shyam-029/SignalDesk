import * as React from "react";
import { Link } from "react-router-dom";
import {
  Eye,
  ListPlus,
  Plus,
  Trash2,
  X,
} from "lucide-react";

import { useBenchmarks, useEtfs, useFunds, useMarketNews, useStockList } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { HeatCell, heatScale } from "@/components/data/HeatCell";
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
import { orderIndexes } from "@/lib/indexOrder";
import { BreadthPanel, NiftyHeat, SectorMoves } from "@/components/markets/MarketPanels";

/**
 * MarketsPage: the daily dashboard, read top to bottom from the widest view
 * to the narrowest. Index cards; then what the whole market did (breadth and
 * the typical move per sector); then the Nifty 50 one tile per company; then
 * gainers and losers side by side with ETF and fund tables, beside a narrow
 * column of headlines and device-local lists.
 */

const BUCKETS = [
  { key: "", label: "All" },
  { key: "large", label: "Large cap" },
  { key: "mid", label: "Mid cap" },
  { key: "small", label: "Small cap" },
] as const;

export default function MarketsPage() {
  return (
    <div className="mx-auto max-w-[1500px] px-4 py-10 md:px-6">
      <SectionHeader kicker="Daily close" title="Markets" />

      {/* 1. The headline numbers. */}
      <IndexStrip />

      {/* 2. What the whole market did: breadth and sectors. */}
      <div className="mt-6 grid gap-6 lg:grid-cols-12">
        <BreadthPanel className="lg:col-span-5" />
        <SectorMoves className="lg:col-span-7" />
      </div>

      {/* 3. The large caps, one tile each. */}
      <NiftyHeat className="mt-6" />

      {/* 4. Names and products take the width; news and your own lists sit
          in a narrow column beside them. */}
      <div className="mt-6 grid gap-6 lg:grid-cols-12">
        <div className="space-y-6 lg:col-span-9">
          <MoversPanel />
          <div className="grid gap-6 xl:grid-cols-2">
            <EtfPanel />
            <FundPanel />
          </div>
        </div>
        <div className="space-y-6 lg:col-span-3">
          <MarketNewsPanel />
          <RecentlyViewed />
          <WatchlistPanel />
        </div>
      </div>

      <p className="mt-6 text-xs text-faint">
        Prices are daily closes. Watchlists and recently viewed are stored on this device.
      </p>
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
      <path d={d} fill="none" stroke={positive ? "var(--up)" : "var(--down)"} strokeWidth="1.5" />
    </svg>
  );
}

function IndexStrip() {
  const query = useBenchmarks();
  const cards = orderIndexes(query.data?.items ?? []);
  // Eight indexes: rows of two (phone) or four (wider), so every row is full.
  return (
    <div className="grid grid-cols-2 gap-px border border-line bg-line lg:grid-cols-5">
      {(cards.length > 0 ? cards : Array.from({ length: 8 }, () => null)).map((c, i) => (
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
                  c.change_pct == null ? "text-faint" : c.change_pct >= 0 ? "text-up" : "text-down",
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

const MOVER_ROWS = 8;

/**
 * Gainers and losers side by side, sharing one size-class filter. Each row's
 * underline is its move relative to the largest move on that side.
 */
function MoversPanel() {
  const [bucket, setBucket] = React.useState<string>("");
  const gainers = useStockList(1, MOVER_ROWS, undefined, "change_pct", "desc", bucket || undefined);
  const losers = useStockList(1, MOVER_ROWS, undefined, "change_pct", "asc", bucket || undefined);

  return (
    <div className="border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <p className="text-sm font-semibold">Biggest moves today</p>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Company size">
          {BUCKETS.map((b) => (
            <button
              key={b.key}
              type="button"
              onClick={() => setBucket(b.key)}
              aria-pressed={bucket === b.key}
              className={cn(
                "border px-2.5 py-1 text-xs font-medium transition-colors",
                bucket === b.key
                  ? "border-cobalt text-foreground"
                  : "border-line text-muted hover:text-foreground",
              )}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>
      <div className="grid md:grid-cols-2 md:divide-x md:divide-line">
        <MoverSide title="Gainers" query={gainers} tone="up" />
        <MoverSide title="Losers" query={losers} tone="down" />
      </div>
    </div>
  );
}

function MoverSide({
  title,
  query,
  tone,
}: {
  title: string;
  query: ReturnType<typeof useStockList>;
  tone: "up" | "down";
}) {
  const items = (query.data?.items ?? []).filter((s) => s.change_pct != null);
  const max = Math.max(0.01, ...items.map((s) => Math.abs(s.change_pct ?? 0)));
  return (
    <div>
      <p className={cn("label-caps border-b border-line px-5 py-2", tone === "up" ? "!text-up" : "!text-down")}>
        {title}
      </p>
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={Boolean(query.data) && items.length === 0}
        emptyTitle="No priced stocks in this size class yet"
        emptyMessage="Today's closes have not been stored for it yet."
        compact
      >
        <ol>
          {items.map((s, i) => {
            const bare = s.symbol.replace(".NS", "");
            return (
              <li key={s.symbol} className="relative border-b border-line last:border-b-0">
                <Link
                  to={`/stocks/${encodeURIComponent(bare)}`}
                  className="flex items-center gap-3 px-5 py-2.5 transition-colors hover:bg-surface-2/60"
                >
                  <span className="num w-4 text-xs text-faint">{i + 1}</span>
                  <StockLogo symbol={s.symbol} name={s.name} size="sm" />
                  <span className="min-w-0 flex-1">
                    <span className="tkr block text-sm">{bare}</span>
                    <span className="block truncate text-xs text-muted">{s.name}</span>
                  </span>
                  <span className="num w-24 text-right text-sm text-muted">{fmtPrice(s.last_price)}</span>
                  <span
                    className={cn(
                      "num w-20 text-right text-sm font-semibold",
                      tone === "up" ? "text-up" : "text-down",
                    )}
                  >
                    {fmtSignedPct(s.change_pct)}
                  </span>
                </Link>
                <span
                  aria-hidden
                  className="absolute bottom-0 left-0 h-0.5"
                  style={{
                    width: `${Math.round((Math.abs(s.change_pct ?? 0) / max) * 100)}%`,
                    background: tone === "up" ? "var(--up)" : "var(--down)",
                    opacity: 0.6,
                  }}
                />
              </li>
            );
          })}
        </ol>
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
                <span className="tkr block text-xs font-semibold">{r.symbol.replace(".NS", "")}</span>
                <span className="block truncate text-xs text-muted">{r.name}</span>
              </span>
              <span className="num text-right text-xs">
                <span className="block">{r.lastPrice != null ? fmtPrice(r.lastPrice) : "-"}</span>
                <span
                  className={cn(
                    "block font-medium",
                    (r.changePct ?? 0) >= 0 ? "text-up" : "text-down",
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
                      className="text-faint transition-colors hover:text-down"
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
                      <Link to={`/stocks/${encodeURIComponent(sym)}`} className="tkr hover:underline">
                        {sym.replace(".NS", "")}
                      </Link>
                      <button
                        type="button"
                        aria-label={`Remove ${sym}`}
                        onClick={() => removeFromWatchlist(l.id, sym)}
                        className="text-faint hover:text-down"
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

const NEWS_TONE: Record<string, string> = {
  positive: "text-up",
  negative: "text-down",
  neutral: "text-faint",
};

/** A narrow headline column: ticker, tone, then the headline. */
function MarketNewsPanel() {
  const query = useMarketNews(18);
  const items = query.data?.items ?? [];
  return (
    <div className="border border-line bg-surface">
      <p className="border-b border-line px-4 py-3 text-sm font-semibold">Headlines</p>
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={items.length === 0}
        emptyTitle="No articles yet"
        emptyMessage="News ingestion has not filled today's feed yet."
        compact
      >
        <ul className="max-h-[640px] divide-y divide-line overflow-y-auto">
          {items.map((a) => (
            <li key={a.id} className="px-4 py-2.5">
              <p className="flex items-baseline justify-between gap-2 text-xs">
                <Link
                  to={`/stocks/${encodeURIComponent(a.symbol.replace(".NS", ""))}`}
                  className="tkr text-muted hover:text-cobalt dark:hover:text-cobalt-strong"
                >
                  {a.symbol.replace(".NS", "")}
                </Link>
                {a.sentiment && (
                  <span className={cn("font-medium capitalize", NEWS_TONE[a.sentiment] ?? "text-faint")}>
                    {a.sentiment}
                  </span>
                )}
              </p>
              <a
                href={a.url}
                target="_blank"
                rel="noreferrer"
                className="mt-1 block text-[13px] leading-snug underline-offset-4 hover:underline"
              >
                {a.title}
              </a>
              <p className="mt-1 text-xs text-faint">
                {a.source}
                {a.published_at ? ` · ${new Date(a.published_at).toLocaleDateString("en-IN")}` : ""}
              </p>
            </li>
          ))}
        </ul>
      </DataState>
    </div>
  );
}

/* --- ETF + fund tables ------------------------------------------------------------ */

const PRODUCT_ROWS = 8;

function PanelHead({ title, to, linkLabel }: { title: string; to: string; linkLabel: string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-line px-5 py-3">
      <p className="text-sm font-semibold">{title}</p>
      <Link to={to} className="text-xs text-cobalt hover:underline dark:text-cobalt-strong">
        {linkLabel}
      </Link>
    </div>
  );
}

/** ETFs ranked by one-year return, with today's move beside it. */
function EtfPanel() {
  const query = useEtfs();
  const all = query.data?.items ?? [];
  const items = [...all]
    .sort((a, b) => (b.return_1y_pct ?? -Infinity) - (a.return_1y_pct ?? -Infinity))
    .slice(0, PRODUCT_ROWS);
  const dayScale = heatScale(all.map((e) => e.change_pct));
  const yearScale = heatScale(all.map((e) => e.return_1y_pct));
  return (
    <div className="border border-line bg-surface">
      <PanelHead title="ETFs, best one-year return" to="/etfs" linkLabel="All ETFs" />
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={Boolean(query.data) && items.length === 0}
        emptyTitle="No ETFs yet"
        emptyMessage="The ETF catalog fills in when ingestion runs."
        compact
      >
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="label-caps px-5 py-2">Fund</th>
              <th scope="col" className="label-caps px-2 py-2 text-right">Price</th>
              <th scope="col" className="label-caps w-20 px-2 py-2 text-right">Today</th>
              <th scope="col" className="label-caps w-20 px-2 py-2 text-right">1Y</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.symbol} className="border-b border-line last:border-b-0">
                <td className="px-5 py-2">
                  <Link to={`/stocks/${encodeURIComponent(e.symbol)}`} className="group block">
                    <span className="tkr block text-sm group-hover:text-cobalt dark:group-hover:text-cobalt-strong">
                      {e.symbol.replace(".NS", "")}
                    </span>
                    <span className="block max-w-56 truncate text-xs text-muted">{e.name}</span>
                  </Link>
                </td>
                <td className="num px-2 py-2 text-right text-sm">{fmtPrice(e.last_price)}</td>
                <td className="p-0.5">
                  <HeatCell value={e.change_pct} scale={dayScale} />
                </td>
                <td className="p-0.5">
                  <HeatCell value={e.return_1y_pct} scale={yearScale} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </div>
  );
}

/** Mutual funds ranked by one-year return, with shorter windows beside it. */
function FundPanel() {
  const query = useFunds("return_1y", "desc");
  const all = query.data?.items ?? [];
  const items = all.slice(0, PRODUCT_ROWS);
  const s1m = heatScale(all.map((f) => f.return_1m_pct));
  const s6m = heatScale(all.map((f) => f.return_6m_pct));
  const s1y = heatScale(all.map((f) => f.return_1y_pct));
  return (
    <div className="border border-line bg-surface">
      <PanelHead title="Mutual funds, best one-year return" to="/funds" linkLabel="All funds" />
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={Boolean(query.data) && items.length === 0}
        emptyTitle="No funds yet"
        emptyMessage="The fund catalog fills in when ingestion runs."
        compact
      >
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="label-caps px-5 py-2">Scheme</th>
              <th scope="col" className="label-caps w-20 px-2 py-2 text-right">1M</th>
              <th scope="col" className="label-caps w-20 px-2 py-2 text-right">6M</th>
              <th scope="col" className="label-caps w-20 px-2 py-2 text-right">1Y</th>
            </tr>
          </thead>
          <tbody>
            {items.map((f) => (
              <tr key={f.id} className="border-b border-line last:border-b-0">
                <td className="px-5 py-2">
                  <Link to={`/funds/${f.id}`} className="group block">
                    <span className="block max-w-64 truncate text-sm font-medium group-hover:text-cobalt dark:group-hover:text-cobalt-strong">
                      {f.name}
                    </span>
                    <span className="block text-xs text-muted">{f.category ?? "-"}</span>
                  </Link>
                </td>
                <td className="p-0.5">
                  <HeatCell value={f.return_1m_pct} scale={s1m} />
                </td>
                <td className="p-0.5">
                  <HeatCell value={f.return_6m_pct} scale={s6m} />
                </td>
                <td className="p-0.5">
                  <HeatCell value={f.return_1y_pct} scale={s1y} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </div>
  );
}
