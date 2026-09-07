import { Link } from "react-router-dom";
import { Activity } from "lucide-react";

import { useStockList } from "@/lib/hooks";
import type { StockSummary } from "@/lib/types";
import { DataState } from "@/components/data/DataState";
import { useReducedMotionSafe } from "@/components/motion/Reveal";
import { cn } from "@/lib/utils";

export interface Mover {
  symbol: string;
  name: string;
  lastPrice: number | null;
  changePct: number;
}

/**
 * Largest absolute daily moves first, capped at `count`. Reads only the real
 * /stocks response; nothing is estimated, padded, or fabricated. Stocks with
 * no price bars (null change) are excluded rather than treated as 0%.
 */
export function pickTopMovers(items: StockSummary[], count = 7): Mover[] {
  return items
    .filter((s): s is StockSummary & { change_pct: number; last_price: number } =>
      s.change_pct != null && s.last_price != null && Number.isFinite(s.change_pct),
    )
    .slice()
    .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
    .slice(0, count)
    .map((s) => ({
      symbol: s.symbol,
      name: s.name,
      lastPrice: s.last_price,
      changePct: s.change_pct,
    }));
}

function PulseChip({ s }: { s: StockSummary }) {
  return (
    <Link
      to={`/stocks/${s.symbol.replace(".NS", "")}`}
      title={s.name}
      className="flex shrink-0 items-baseline gap-2 border border-cobalt/20 bg-surface px-2.5 py-1 transition-colors hover:border-cobalt/70 hover:bg-surface-2"
    >
      <span className="num text-xs font-semibold text-cobalt dark:text-cobalt-strong">
        {s.symbol.replace(".NS", "")}
      </span>
      <span
        className={cn(
          "num text-xs font-medium",
          s.change_pct == null
            ? "text-faint"
            : s.change_pct >= 0
              ? "text-band-positive"
              : "text-band-weak",
        )}
      >
        {s.change_pct == null ? "-" : `${s.change_pct > 0 ? "+" : ""}${s.change_pct.toFixed(2)}%`}
      </span>
    </Link>
  );
}

const skeletonRow = (
  <div className="flex gap-2 overflow-hidden">
    {Array.from({ length: 6 }).map((_, i) => (
      <div key={i} className="h-7 w-28 shrink-0 animate-pulse bg-surface-2" />
    ))}
  </div>
);

/**
 * Continuous strip of EVERY catalog constituent (the Nifty 250), auto-scrolling
 * through the real /stocks response. Pauses on hover; under reduced motion it
 * renders as a plain scrollable row. Static chips, not a fabricated ticker.
 */
export function MarketPulse() {
  const list = useStockList(1, 200);
  const reduced = useReducedMotionSafe();
  const stocks = list.data?.items.filter((s) => Number.isFinite(s.change_pct)) ?? [];

  return (
    <aside aria-label="Market pulse" className="border-b border-cobalt/20 bg-cobalt/[0.045]">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-2.5 md:px-6">
        <p className="label-caps flex shrink-0 items-center gap-1.5" style={{ color: "var(--cobalt)" }}>
          <Activity className="size-3.5" />
          Market pulse
        </p>
        <DataState
          loading={list.isLoading}
          error={list.error}
          onRetry={list.refetch}
          empty={Boolean(list.data) && stocks.length === 0}
          emptyTitle="No market data"
          emptyMessage="No stored quotes to show yet."
          skeleton={skeletonRow}
          compact
          className="min-w-0 flex-1"
        >
          {reduced ? (
            <div className="flex min-w-0 items-center gap-2 overflow-x-auto">
              {stocks.map((s) => (
                <PulseChip key={s.symbol} s={s} />
              ))}
            </div>
          ) : (
            <div className="marquee relative min-w-0 flex-1 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_28px,black_calc(100%-28px),transparent)]">
              <div className="marquee-track flex w-max items-center gap-2">
                {[0, 1].map((dup) => (
                  <div
                    key={dup}
                    className="flex items-center gap-2"
                    aria-hidden={dup === 1}
                  >
                    {stocks.map((s) => (
                      <PulseChip key={`${dup}-${s.symbol}`} s={s} />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
          <span className="num hidden shrink-0 pl-1 text-xs text-faint lg:inline">
            all {stocks.length || 50} constituents Â· latest close
          </span>
        </DataState>
      </div>
    </aside>
  );
}

