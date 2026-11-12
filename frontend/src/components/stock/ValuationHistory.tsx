import * as React from "react";

import { useValuationHistory } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { TimeSeriesChart, type TimeSeriesLine } from "@/components/chart/TimeSeriesChart";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { MultipleBand } from "@/lib/types";

/**
 * ValuationHistory: each multiple against the stock's OWN past, the
 * companion to the peer verdict above it ("cheap vs peers" and "cheap vs its
 * own history" are different questions). Everything is computed by the
 * backend's /valuation-history endpoint; this component only renders. A
 * multiple that cannot be computed says why and shows no numbers.
 */

const LABELS: Record<MultipleBand["metric"], string> = {
  pe: "P/E",
  pb: "P/B",
  ps: "P/S",
};

const BASIS: Record<MultipleBand["metric"], string> = {
  pe: "full-year profit",
  pb: "year-end book value",
  ps: "full-year sales",
};

const REASONS: Record<string, string> = {
  no_price_history: "No price history is stored for this stock yet.",
  missing_share_count:
    "The share count cannot be worked out from the stored figures, so past market value is unknown.",
  missing_inputs: "The full-year figure this multiple needs is not stored for this stock.",
  insufficient_history:
    "Too few days have a valid reading to draw a meaningful range.",
  no_current_reading:
    "The latest full-year figure is a loss or is missing, so there is no reading for today to compare.",
  non_applicable_financial:
    "Sales are not a meaningful base for banks and other financial companies.",
};

const VERDICT_TONE: Record<string, string> = {
  below: "text-band-positive",
  near: "text-foreground",
  above: "text-band-weak",
};

function verdictText(band: MultipleBand): string {
  const label = LABELS[band.metric];
  const gap = Math.abs(band.vs_median_pct ?? 0).toFixed(0);
  if (band.verdict === "below") return `${label} is ${gap}% below its own median`;
  if (band.verdict === "above") return `${label} is ${gap}% above its own median`;
  return `${label} is close to its own median`;
}

export function ValuationHistory({ symbol }: { symbol: string }) {
  const query = useValuationHistory(symbol);
  const data = query.data;
  const bands = data?.multiples ?? [];
  const firstAvailable = bands.find((b) => b.status === "available")?.metric ?? "pe";
  const [picked, setPicked] = React.useState<MultipleBand["metric"] | null>(null);
  const metric = picked ?? firstAvailable;
  const band = bands.find((b) => b.metric === metric);

  const lines = React.useMemo<TimeSeriesLine[]>(() => {
    if (!band || band.status !== "available" || band.median == null) return [];
    return [
      {
        key: "multiple",
        label: LABELS[band.metric],
        color: "--cobalt",
        width: 2,
        data: band.series.map((p) => ({ time: p.date, value: p.value })),
      },
      {
        key: "median",
        label: "Own median",
        color: "--faint",
        width: 1,
        data: band.series.map((p) => ({ time: p.date, value: band.median })),
      },
    ];
  }, [band]);

  return (
    <div className="border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div>
          <p className="label-caps">Against its own history</p>
          {data?.from_date && data.to_date && (
            <p className="num mt-0.5 text-xs text-faint">
              {fmtDate(data.from_date)} to {fmtDate(data.to_date)}
            </p>
          )}
        </div>
        <div role="group" aria-label="Multiple" className="flex border border-line">
          {bands.map((b) => (
            <button
              key={b.metric}
              type="button"
              onClick={() => setPicked(b.metric)}
              aria-pressed={b.metric === metric}
              className={cn(
                "px-3 py-1.5 text-xs font-medium transition-colors",
                b.metric === metric
                  ? "bg-surface-2 text-foreground"
                  : "text-muted hover:text-foreground",
              )}
            >
              {LABELS[b.metric]}
            </button>
          ))}
        </div>
      </div>

      <div className="p-5">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          compact
        >
          {data?.suspect_move_pct != null && (
            <p className="mb-5 border border-rule bg-surface-2 px-4 py-3 text-xs leading-relaxed text-muted">
              <span className="font-semibold text-foreground">Check the data. </span>
              The stored prices show a one-day move of{" "}
              <span className="num font-medium">{data.suspect_move_pct.toFixed(1)}%</span> on{" "}
              {fmtDate(data.suspect_move_date)}, which is usually a share split or bonus that
              has not been adjusted for. Days before it are left out here because they are not
              comparable with today&rsquo;s.
            </p>
          )}

          {band && band.status !== "available" && (
            <div>
              <p className="num text-2xl font-medium text-faint">-</p>
              <p className="mt-2 max-w-xl text-xs leading-relaxed text-muted">
                {band.status === "not_applicable" ? "Not applicable. " : "Not computable. "}
                {REASONS[band.reason ?? ""] ?? "The stored data does not support this multiple."}{" "}
                Nothing is estimated.
              </p>
            </div>
          )}

          {band && band.status === "available" && (
            <div className="grid gap-8 lg:grid-cols-12">
              <div className="lg:col-span-5">
                <p
                  className={cn(
                    "font-display text-2xl font-semibold",
                    VERDICT_TONE[band.verdict ?? "near"],
                  )}
                >
                  {verdictText(band)}
                </p>
                <p className="num mt-1 text-sm text-muted">
                  {LABELS[band.metric]} {band.current?.toFixed(1)} today vs own median{" "}
                  {band.median?.toFixed(1)}
                </p>

                <div className="mt-6">
                  <RangeBar band={band} />
                </div>

                <dl className="num mt-6 grid grid-cols-3 gap-px border border-line bg-line text-xs">
                  <Stat label="Lowest" value={band.low?.toFixed(1)} />
                  <Stat label="Median" value={band.median?.toFixed(1)} />
                  <Stat label="Highest" value={band.high?.toFixed(1)} />
                </dl>
                {band.percentile != null && (
                  <p className="mt-3 text-xs leading-relaxed text-muted">
                    It was cheaper than today on{" "}
                    <span className="num font-medium text-foreground">
                      {band.percentile.toFixed(0)}%
                    </span>{" "}
                    of the days in this period.
                  </p>
                )}
              </div>

              <div className="lg:col-span-7">
                <TimeSeriesChart
                  lines={lines}
                  height={240}
                  valueFormatter={(v) => v.toFixed(1)}
                />
              </div>
            </div>
          )}

          {data && (
            <p className="mt-5 border-t border-line pt-3 text-xs leading-relaxed text-faint">
              Each past day uses the latest {band ? BASIS[band.metric] : "full-year figure"}{" "}
              that had been published by then (results count as public{" "}
              {data.publication_lag_days} days after the year ends) and today&rsquo;s share
              count. Share issues and buybacks inside the period are not adjusted for. The
              period is as long as the stored price history.
            </p>
          )}
        </DataState>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | undefined }) {
  return (
    <div className="bg-surface px-3 py-2.5">
      <dt className="text-faint">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium">{value ?? "-"}</dd>
    </div>
  );
}

/** Low-to-high range with the median tick and today's reading as a dot. */
function RangeBar({ band }: { band: MultipleBand }) {
  const { low, high, median, current } = band;
  if (low == null || high == null || median == null || current == null) return null;
  const span = high - low;
  const pct = (v: number) => (span > 0 ? ((v - low) / span) * 100 : 50);
  const clamp = (v: number) => Math.min(98, Math.max(2, v));
  const tone =
    band.verdict === "below"
      ? "var(--band-positive)"
      : band.verdict === "above"
        ? "var(--band-weak)"
        : "var(--muted)";
  return (
    <div>
      <div className="relative h-6">
        <div className="absolute inset-x-0 top-3 h-px bg-rule" />
        <span
          className="absolute top-1 block h-4 w-px bg-cobalt"
          style={{ left: `${clamp(pct(median))}%` }}
        />
        <span
          className="absolute top-3 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{ left: `${clamp(pct(current))}%`, background: tone }}
        />
      </div>
      <p className="flex justify-between text-xs font-medium text-faint">
        <span>Cheapest it has been</span>
        <span>Priciest it has been</span>
      </p>
    </div>
  );
}
