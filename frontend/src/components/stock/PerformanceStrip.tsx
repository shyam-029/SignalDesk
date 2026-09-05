import { usePerformance } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { InfoDot } from "@/components/data/InfoDot";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

const WINDOWS: Array<{ key: string; label: string }> = [
  { key: "1w", label: "1W" },
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6mo", label: "6M" },
  { key: "1y", label: "1Y" },
];

/**
 * PerformanceStrip: compact windowed price performance under the stock
 * header (Part D). Every number comes from the backend's /performance
 * endpoint; the frontend only formats. Windows without enough history show
 * "-" (a missing window is data honestly absent, not zero), and the whole
 * strip degrades to an insufficient-data note until at least two bars exist.
 */
export function PerformanceStrip({ symbol }: { symbol: string }) {
  const query = usePerformance(symbol);
  const perf = query.data;

  return (
    <section id="performance" aria-label="Price performance">
      <div className="border-b border-line bg-surface-2/30">
        <div className="mx-auto max-w-6xl px-4 py-4 md:px-6">
          <DataState
            loading={query.isLoading}
            error={query.error}
            onRetry={query.refetch}
            insufficient={Boolean(perf?.insufficient_data)}
            insufficientTitle="Not enough price history"
            insufficientMessage="Performance windows and volatility need at least two stored daily bars. Nothing is estimated in the meantime."
            skeleton={
              <div className="flex flex-wrap gap-x-8 gap-y-3">
                {WINDOWS.map((w) => (
                  <div key={w.key} className="space-y-1.5">
                    <div className="h-3 w-6 animate-pulse bg-surface-2" />
                    <div className="h-4 w-14 animate-pulse bg-surface-2" />
                  </div>
                ))}
              </div>
            }
            compact
          >
            {perf && (
              <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
                <p className="label-caps flex items-center gap-1.5">
                  Performance
                  <InfoDot metric="performance" className="size-3.5" />
                </p>
                {WINDOWS.map((w) => {
                  const win = perf.windows[w.key];
                  const pct = win?.change_pct;
                  return (
                    <div key={w.key} className="min-w-14">
                      <p className="num text-xs text-faint">{w.label}</p>
                      <p
                        className={cn(
                          "num text-sm font-medium",
                          pct == null ? "text-faint" : pct > 0 ? "text-band-positive" : pct < 0 ? "text-band-weak" : "text-muted",
                        )}
                        title={pct == null ? "Not enough history for this window" : undefined}
                      >
                        {fmtSignedPct(pct)}
                      </p>
                    </div>
                  );
                })}
                <div className="min-w-32">
                  <p className="num text-xs text-faint">52W range</p>
                  <p className="num text-sm font-medium">
                    {perf.low_52w != null && perf.high_52w != null
                      ? `${fmtPrice(perf.low_52w)} - ${fmtPrice(perf.high_52w)}`
                      : "-"}
                  </p>
                </div>
                <div className="min-w-20">
                  <p className="label-caps flex items-center gap-1 text-xs">
                    <span className="num text-faint">Vol 1Y</span>
                    <InfoDot metric="volatility" className="size-3" />
                  </p>
                  <p className="num text-sm font-medium">
                    {perf.volatility_1y_pct != null
                      ? `${perf.volatility_1y_pct.toFixed(1)}%`
                      : "-"}
                  </p>
                </div>
                {perf.as_of && (
                  <p className="num ml-auto text-xs text-faint">
                    as of {perf.as_of} · {perf.bars_used} bars
                  </p>
                )}
              </div>
            )}
          </DataState>
        </div>
      </div>
    </section>
  );
}
