import * as React from "react";
import { Link } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { StockSummary } from "@/lib/types";
import { useNifty50 } from "@/lib/nifty50";
import { DataState } from "@/components/data/DataState";
import { fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Market-wide panels for the Markets page, all computed in the browser from
 * the stored daily moves of the ranked universe (four list pages of 250,
 * shared between the panels by query key):
 *
 *   BreadthPanel  how much of the market rose or fell, and by how much
 *   SectorMoves   the typical (median) move in each sector, best to worst
 *   NiftyHeat     the Nifty 50 as one tinted tile per company
 *
 * A stock without a stored move for the day is left out of every figure
 * rather than counted as flat.
 */

const PAGES = [1, 2, 3, 4];

/** Every ranked stock with a stored move today. */
function useUniverseMoves() {
  const results = useQueries({
    queries: PAGES.map((page) => ({
      // Same key shape as useStockList, so these pages are shared app-wide.
      queryKey: ["stocks", page, 250, null, "market_cap", "desc", null],
      queryFn: () => api.stocks(page, 250, undefined, "market_cap", "desc"),
      staleTime: 60_000,
    })),
  });
  const loadedKey = results.map((q) => q.dataUpdatedAt).join("-");
  const items = React.useMemo(
    () => results.flatMap((q) => q.data?.items ?? []).filter((s) => s.change_pct != null),
    [loadedKey], // eslint-disable-line react-hooks/exhaustive-deps
  );
  return {
    items,
    isLoading: results.some((q) => q.isLoading),
    error: results.every((q) => q.isError) ? (results[0].error as Error) : null,
    refetch: () => results.forEach((q) => void q.refetch()),
  };
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function Panel({
  title,
  aside,
  children,
  className,
}: {
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col border border-line bg-surface", className)}>
      <div className="flex items-baseline justify-between gap-3 border-b border-line px-5 py-3">
        <p className="text-sm font-semibold">{title}</p>
        {aside}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}

/* --- Breadth ---------------------------------------------------------------- */

// Day-move buckets, in percent. Outer buckets are open-ended.
const BUCKETS: Array<{ label: string; lo: number; hi: number; up: boolean }> = [
  { label: "< -3", lo: -Infinity, hi: -3, up: false },
  { label: "-3 to -2", lo: -3, hi: -2, up: false },
  { label: "-2 to -1", lo: -2, hi: -1, up: false },
  { label: "-1 to 0", lo: -1, hi: 0, up: false },
  { label: "0 to 1", lo: 0, hi: 1, up: true },
  { label: "1 to 2", lo: 1, hi: 2, up: true },
  { label: "2 to 3", lo: 2, hi: 3, up: true },
  { label: "> 3", lo: 3, hi: Infinity, up: true },
];

export function BreadthPanel({ className }: { className?: string }) {
  const universe = useUniverseMoves();
  const moves = universe.items.map((s) => s.change_pct as number);
  const n = moves.length;
  const rose = moves.filter((m) => m > 0).length;
  const fell = moves.filter((m) => m < 0).length;
  const flat = n - rose - fell;
  const share = (k: number) => (n > 0 ? (k / n) * 100 : 0);
  const med = median(moves);

  const counts = BUCKETS.map(
    (b) => moves.filter((m) => (b.up ? m >= b.lo && m < b.hi : m >= b.lo && m < b.hi)).length,
  );
  // 0 exactly belongs to "0 to 1"; the open top bucket takes m >= 3.
  const peak = Math.max(1, ...counts);

  return (
    <Panel
      title="Breadth"
      className={className}
      aside={
        med != null ? (
          <p className="text-xs text-muted">
            Typical stock{" "}
            <span className={cn("num font-semibold", med >= 0 ? "text-up" : "text-down")}>
              {fmtSignedPct(med)}
            </span>
          </p>
        ) : undefined
      }
    >
      <DataState
        loading={universe.isLoading && n === 0}
        error={universe.error}
        onRetry={universe.refetch}
        empty={!universe.isLoading && n === 0}
        emptyTitle="No moves stored yet"
        emptyMessage="Today's closes have not been stored yet."
        compact
      >
        <div className="px-5 py-5">
          {/* Rose / flat / fell as one bar. */}
          <div className="flex items-baseline justify-between">
            <p>
              <span className="num text-2xl font-semibold text-up">{Math.round(share(rose))}%</span>
              <span className="ml-2 text-xs text-muted">rose</span>
            </p>
            <p>
              <span className="mr-2 text-xs text-muted">fell</span>
              <span className="num text-2xl font-semibold text-down">{Math.round(share(fell))}%</span>
            </p>
          </div>
          <div
            className="mt-2 flex h-2.5 w-full overflow-hidden"
            role="img"
            aria-label={`${Math.round(share(rose))}% of stocks rose, ${Math.round(share(fell))}% fell`}
          >
            <span style={{ width: `${share(rose)}%`, background: "var(--up)" }} />
            <span style={{ width: `${share(flat)}%`, background: "var(--rule)" }} />
            <span style={{ width: `${share(fell)}%`, background: "var(--down)" }} />
          </div>

          {/* How big the moves were. */}
          <p className="mt-6 text-xs text-muted">How far stocks moved today (%)</p>
          <div className="mt-3 flex h-28 items-end gap-1.5" aria-hidden>
            {BUCKETS.map((b, i) => (
              <div key={b.label} className="flex h-full flex-1 flex-col justify-end">
                <span
                  className="block w-full"
                  style={{
                    height: `${Math.max(2, (counts[i] / peak) * 100)}%`,
                    background: b.up ? "var(--up)" : "var(--down)",
                    opacity: 0.85,
                  }}
                />
              </div>
            ))}
          </div>
          <div className="mt-1.5 flex gap-1.5 border-t border-line pt-1.5">
            {BUCKETS.map((b, i) => (
              <span key={b.label} className="num flex-1 text-center text-[11px] leading-tight text-faint">
                {b.label}
                <span className="sr-only">: {Math.round(share(counts[i]))}% of stocks</span>
              </span>
            ))}
          </div>
        </div>
      </DataState>
    </Panel>
  );
}

/* --- Sector moves ------------------------------------------------------------ */

/** Sectors with fewer priced stocks than this are too thin to summarise. */
const MIN_SECTOR = 8;
const TOP_AND_BOTTOM = 5;

export function SectorMoves({ className }: { className?: string }) {
  const universe = useUniverseMoves();
  const [all, setAll] = React.useState(false);

  const sectors = React.useMemo(() => {
    const groups = new Map<string, number[]>();
    for (const s of universe.items) {
      if (!s.sector) continue;
      const list = groups.get(s.sector);
      if (list) list.push(s.change_pct as number);
      else groups.set(s.sector, [s.change_pct as number]);
    }
    return [...groups.entries()]
      .filter(([, v]) => v.length >= MIN_SECTOR)
      .map(([sector, v]) => ({
        sector,
        move: median(v) as number,
        rose: (v.filter((m) => m > 0).length / v.length) * 100,
      }))
      .sort((a, b) => b.move - a.move);
  }, [universe.items]);

  const scale = Math.max(0.1, ...sectors.map((s) => Math.abs(s.move)));
  const trimmed = sectors.length > TOP_AND_BOTTOM * 2 + 1;
  const best = sectors.slice(0, TOP_AND_BOTTOM);
  const worst = sectors.slice(-TOP_AND_BOTTOM);

  return (
    <Panel
      title="Sectors today"
      className={className}
      aside={<p className="text-xs text-muted">Typical move of a stock in the sector</p>}
    >
      <DataState
        loading={universe.isLoading && sectors.length === 0}
        error={universe.error}
        onRetry={universe.refetch}
        empty={!universe.isLoading && sectors.length === 0}
        emptyTitle="No sector moves yet"
        emptyMessage="Today's closes have not been stored yet."
        compact
      >
        <div className="py-2">
          {all || !trimmed ? (
            sectors.map((s) => <SectorRow key={s.sector} s={s} scale={scale} />)
          ) : (
            <>
              {best.map((s) => (
                <SectorRow key={s.sector} s={s} scale={scale} />
              ))}
              <p className="px-5 py-1 text-center text-xs text-faint" aria-hidden>
                ···
              </p>
              {worst.map((s) => (
                <SectorRow key={s.sector} s={s} scale={scale} />
              ))}
            </>
          )}
        </div>
        {trimmed && (
          <button
            type="button"
            onClick={() => setAll((v) => !v)}
            aria-expanded={all}
            className="w-full border-t border-line px-5 py-2.5 text-left text-xs font-medium text-muted transition-colors hover:text-foreground"
          >
            {all ? "Show best and worst only" : "Show all sectors"}
          </button>
        )}
      </DataState>
    </Panel>
  );
}

function SectorRow({
  s,
  scale,
}: {
  s: { sector: string; move: number; rose: number };
  scale: number;
}) {
  const half = Math.min(50, (Math.abs(s.move) / scale) * 50);
  const up = s.move >= 0;
  return (
    <Link
      to={`/screener?sector=${encodeURIComponent(s.sector)}`}
      title={`${Math.round(s.rose)}% of ${s.sector} stocks rose`}
      className="flex items-center gap-3 px-5 py-1.5 transition-colors hover:bg-surface-2/60"
    >
      <span className="w-44 shrink-0 truncate text-sm">{s.sector}</span>
      <span className="relative block h-3.5 flex-1" aria-hidden>
        <span className="absolute inset-y-0 left-1/2 w-px bg-rule" />
        <span
          className="absolute inset-y-0.5"
          style={{
            background: up ? "var(--up)" : "var(--down)",
            width: `${half}%`,
            left: up ? "50%" : `${50 - half}%`,
          }}
        />
      </span>
      <span className={cn("num w-16 shrink-0 text-right text-sm font-medium", up ? "text-up" : "text-down")}>
        {fmtSignedPct(s.move)}
      </span>
    </Link>
  );
}

/* --- Nifty 50 heat ------------------------------------------------------------ */

export function NiftyHeat({ className }: { className?: string }) {
  const nifty = useNifty50();
  const items = nifty.items;
  const scale = Math.max(0.5, ...items.map((s) => Math.abs(s.change_pct ?? 0)));
  const rose = items.filter((s) => (s.change_pct ?? 0) > 0).length;

  return (
    <Panel
      title="Nifty 50, company by company"
      className={className}
      aside={
        items.length > 0 ? (
          <p className="num text-xs">
            <span className="text-up">{rose} up</span>
            <span className="text-faint"> · </span>
            <span className="text-down">{items.length - rose} down</span>
          </p>
        ) : undefined
      }
    >
      <DataState
        loading={nifty.isLoading}
        error={nifty.error}
        onRetry={nifty.refetch}
        empty={!nifty.isLoading && items.length === 0}
        emptyTitle="No moves stored yet"
        emptyMessage="Today's closes have not been stored yet."
        compact
      >
        <div className="grid grid-cols-3 gap-1.5 p-3 sm:grid-cols-5 lg:grid-cols-10">
          {items.map((s) => (
            <HeatTile key={s.symbol} s={s} scale={scale} />
          ))}
        </div>
      </DataState>
    </Panel>
  );
}

function HeatTile({ s, scale }: { s: StockSummary; scale: number }) {
  const move = s.change_pct ?? 0;
  const tint = Math.round(10 + Math.min(1, Math.abs(move) / scale) * 42); // 10% to 52%
  const tone = move >= 0 ? "var(--up)" : "var(--down)";
  const bare = s.symbol.replace(".NS", "");
  return (
    <Link
      to={`/stocks/${encodeURIComponent(bare)}`}
      title={s.name}
      className="block border border-rule bg-surface transition-colors hover:border-foreground"
    >
      <span
        className="flex h-16 flex-col justify-between p-2"
        style={{ background: `color-mix(in srgb, ${tone} ${tint}%, transparent)` }}
      >
        <span className="tkr truncate text-[11px] text-foreground">{bare}</span>
        <span className="num text-sm font-semibold text-foreground">{fmtSignedPct(s.change_pct)}</span>
      </span>
    </Link>
  );
}
