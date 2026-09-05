import { Link } from "react-router-dom";
import { ChevronLeft } from "lucide-react";

import { useStockDetail } from "@/lib/hooks";
import { AskPanel } from "@/components/explain/AskPanel";
import { DataState } from "@/components/data/DataState";
import { InfoDot } from "@/components/data/InfoDot";
import {
  fmtDate,
  fmtMarketCap,
  fmtPrice,
  fmtSigned,
  fmtSignedPct,
} from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * StockHeader: the market snapshot: identity, price, daily movement, size,
 * day range. One API call (GET /stocks/{symbol}); editorial composition, not a
 * row of dashboard cards.
 */
export function StockHeader({ symbol }: { symbol: string }) {
  const query = useStockDetail(symbol);
  const detail = query.data;

  return (
    <header className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 pb-8 pt-6 md:px-6">
        <Link
          to="/markets"
          className="mb-5 inline-flex items-center gap-1 text-xs text-muted hover:text-foreground"
        >
          <ChevronLeft className="size-3.5" /> All stocks
        </Link>

        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          skeleton={
            <div className="space-y-4">
              <div className="h-8 w-72 animate-pulse bg-surface-2" />
              <div className="h-10 w-56 animate-pulse bg-surface-2" />
            </div>
          }
        >
          {detail && (
            <div className="flex flex-wrap items-end justify-between gap-6">
              <div>
                <div className="flex flex-wrap items-baseline gap-3">
                  <h1 className="font-display text-3xl font-semibold tracking-[-0.01em] md:text-4xl">
                    {detail.name}
                  </h1>
                  <span className="num border border-line bg-surface-2 px-1.5 py-0.5 text-xs font-semibold">
                    {detail.symbol}
                  </span>
                </div>
                <p className="mt-1.5 text-sm text-muted">
                  {detail.sector ?? "-"}
                  {detail.industry ? <span className="text-faint"> · {detail.industry}</span> : null}
                </p>
              </div>

              <div className="flex flex-col items-end gap-1">
                <div className="flex items-baseline gap-3">
                  <span className="num text-3xl font-medium md:text-4xl">
                    {fmtPrice(detail.quote.last_price)}
                  </span>
                  {detail.quote.change_pct != null && (
                    <span
                      className={cn(
                        "num text-sm font-medium",
                        detail.quote.change_pct >= 0
                          ? "text-band-positive"
                          : "text-band-weak",
                      )}
                    >
                      {fmtSigned(detail.quote.change_abs)} ({fmtSignedPct(detail.quote.change_pct)})
                    </span>
                  )}
                </div>
                <p className="num text-xs text-faint">
                  {detail.quote.date ? `Close ${fmtDate(detail.quote.date)}` : "No price data"}
                </p>
              </div>
            </div>
          )}

          {detail && (
            <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
              {/* Day statistics: raw metrics stay neutral. */}
              <dl className="num flex flex-wrap gap-x-8 gap-y-2 text-xs">
                <Stat label="Market cap" value={fmtMarketCap(detail.market_cap)} metric="market_cap" />
                <Stat label="Open" value={fmtPrice(detail.quote.open)} />
                <Stat label="Prev close" value={fmtPrice(detail.quote.prev_close)} />
                <Stat label="Day low" value={fmtPrice(detail.quote.low)} />
                <Stat label="Day high" value={fmtPrice(detail.quote.high)} />
              </dl>
              <AskPanel symbol={detail.symbol} displayName={detail.name} />
            </div>
          )}
        </DataState>
      </div>
    </header>
  );
}

function Stat({
  label,
  value,
  metric,
}: {
  label: string;
  value: string;
  metric?: "market_cap";
}) {
  return (
    <div>
      <dt className="flex items-center gap-1 text-xs font-medium uppercase tracking-[0.12em] text-faint">
        {label}
        {metric && <InfoDot metric={metric} className="size-3.5" />}
      </dt>
      <dd className="num mt-0.5 text-sm font-medium">{value}</dd>
    </div>
  );
}
