import { useBenchmarks } from "@/lib/hooks";
import type { BenchmarkCard } from "@/lib/types";
import { DataState } from "@/components/data/DataState";
import { cn } from "@/lib/utils";

/**
 * Display order for the tape: headline indexes, then macro (fx/commodity),
 * then sectors and breadth - matching how a trading terminal orders its
 * strip. Benchmarks missing from the stored set are skipped; anything else
 * stored appends at the end.
 */
const ORDER = [
  "^NSEI",      // NIFTY 50
  "^BSESN",     // SENSEX
  "INR=X",      // USD/INR
  "GC=F",       // GOLD (USD)
  "^INDIAVIX",  // INDIA VIX
  "^NSEMDCP50", // NIFTY MIDCAP 50
  "^NSEBANK",   // NIFTY BANK
  "^CNXIT",     // NIFTY IT
  "^CNXPHARMA", // NIFTY PHARMA
  "^CRSLDX",    // broad market
];

export function orderBenchmarks(items: BenchmarkCard[]): BenchmarkCard[] {
  const bySymbol = new Map(items.map((b) => [b.symbol, b]));
  const ordered: BenchmarkCard[] = [];
  for (const sym of ORDER) {
    const hit = bySymbol.get(sym);
    if (hit) {
      ordered.push(hit);
      bySymbol.delete(sym);
    }
  }
  return [...ordered, ...bySymbol.values()];
}

function IndexChip({ b }: { b: BenchmarkCard }) {
  const up = (b.change_pct ?? 0) >= 0;
  return (
    <span
      className="flex shrink-0 items-baseline gap-2 border border-line bg-surface px-2.5 py-1"
      title={b.name ?? b.symbol}
    >
      <span className="label-caps text-xs text-muted">{b.name ?? b.symbol}</span>
      <span className="num text-xs font-semibold text-foreground">
        {b.latest_close != null
          ? b.latest_close.toLocaleString("en-IN", { maximumFractionDigits: 2 })
          : "-"}
      </span>
      <span
        className={cn(
          "num text-xs font-medium",
          b.change_pct == null ? "text-faint" : up ? "text-up" : "text-down",
        )}
      >
        {b.change_pct == null ? "-" : `${up ? "+" : ""}${b.change_pct.toFixed(2)}%`}
      </span>
    </span>
  );
}

const skeletonRow = (
  <div className="flex gap-2 overflow-hidden">
    {Array.from({ length: 6 }).map((_, i) => (
      <div key={i} className="h-7 w-32 shrink-0 animate-pulse bg-surface-2" />
    ))}
  </div>
);

/**
 * MarketPulse: the landing's index-and-macro tape - NIFTY 50, SENSEX,
 * USD/INR, Gold, India VIX, midcap breadth and the sector indexes
 * (Bank/IT/Pharma), each against its PREVIOUS stored close. Reads only the
 * stored benchmark tables; a macro row with no reliable free source
 * (smallcap) stays absent rather than stale. A static row (it scrolls
 * sideways on narrow screens): the stock ticker above is the one moving strip.
 */
export function MarketPulse() {
  const query = useBenchmarks();
  const cards = orderBenchmarks(query.data?.items ?? []);

  return (
    <aside aria-label="Market pulse: indexes, currency, gold and sectors" className="border-b border-line bg-background">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-2.5 md:px-6">
        <p className="label-caps shrink-0">Indexes</p>
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          empty={Boolean(query.data) && cards.length === 0}
          emptyTitle="No index data"
          emptyMessage="No stored benchmark quotes to show yet."
          skeleton={skeletonRow}
          compact
          className="min-w-0 flex-1"
        >
          <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto [scrollbar-width:none]">
            {cards.map((b) => (
              <IndexChip key={b.symbol} b={b} />
            ))}
          </div>
        </DataState>
      </div>
    </aside>
  );
}
