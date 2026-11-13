import * as React from "react";

import { useRisk } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { CollapsibleSection } from "@/components/stock/CollapsibleSection";
import { TimeSeriesChart, type TimeSeriesLine } from "@/components/chart/TimeSeriesChart";
import { fmtDate } from "@/lib/format";
import type { RiskResponse } from "@/lib/types";

/**
 * RiskSection: how rough the ride has been. Volatility, the deepest fall
 * from a peak (and whether it was recovered), how far the price sits below
 * its peak today, and beta against the NIFTY 50. All figures come from the
 * backend's /risk endpoint over the stored price history; a figure that
 * cannot be computed shows "-". A one-day move too large to be real is
 * called out instead of being silently trusted.
 */

function pct(value: number | null | undefined, digits = 1): string {
  return value == null ? "-" : `${value.toFixed(digits)}%`;
}

export function riskSummary(risk: RiskResponse | undefined): string | null {
  if (!risk || risk.insufficient_data) return null;
  const parts: string[] = [];
  if (risk.volatility_pct != null) parts.push(`Volatility ${pct(risk.volatility_pct)} a year`);
  if (risk.max_drawdown.pct != null) parts.push(`deepest fall ${pct(risk.max_drawdown.pct)}`);
  if (risk.beta != null) parts.push(`beta ${risk.beta.toFixed(2)}`);
  return parts.length > 0 ? parts.join(" · ") : null;
}

function betaText(risk: RiskResponse): string {
  if (risk.beta == null) {
    return `Needs more days of shared history with the ${risk.benchmark_name}.`;
  }
  const b = risk.beta;
  if (b >= 1.15) return `Tends to move more than the ${risk.benchmark_name}.`;
  if (b <= 0.85) return `Tends to move less than the ${risk.benchmark_name}.`;
  return `Tends to move about as much as the ${risk.benchmark_name}.`;
}

function recoveryText(risk: RiskResponse): string {
  const dd = risk.max_drawdown;
  if (dd.pct == null) return "";
  if (dd.pct === 0) return "The price never closed below an earlier peak in this period.";
  const span = `${fmtDate(dd.peak_date)} to ${fmtDate(dd.trough_date)}`;
  if (dd.days_to_recover != null) {
    return `${span}. Back at the old peak ${dd.days_to_recover} days later.`;
  }
  return `${span}. Not yet back at the old peak.`;
}

export function RiskSection({ symbol }: { symbol: string }) {
  const query = useRisk(symbol);
  const risk = query.data;

  const lines = React.useMemo<TimeSeriesLine[]>(() => {
    if (!risk || risk.underwater.length < 2) return [];
    return [
      {
        key: "underwater",
        label: "Below peak",
        color: "--down",
        width: 2,
        data: risk.underwater.map((p) => ({ time: p.date, value: p.value })),
      },
    ];
  }, [risk]);

  return (
    <CollapsibleSection
      id="risk"
      kicker="Risk"
      title="How rough the ride has been"
      summary={riskSummary(risk)}
    >
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        insufficient={risk?.insufficient_data || undefined}
        insufficientTitle="Not enough price history yet"
        insufficientMessage="Risk figures need at least a few days of stored prices. Nothing is estimated."
      >
        {risk && !risk.insufficient_data && (
          <>
            {risk.suspect_move_pct != null && (
              <p className="mb-5 border border-rule bg-surface-2 px-4 py-3 text-xs leading-relaxed text-muted">
                <span className="font-semibold text-foreground">Check the data. </span>
                The stored prices show a one-day move of{" "}
                <span className="num font-medium">{pct(risk.suspect_move_pct)}</span> on{" "}
                {fmtDate(risk.suspect_move_date)}. A move that large is usually a share
                split or bonus that has not been adjusted for, so the figures below may be
                overstated.
              </p>
            )}

            <div className="grid gap-px border border-line bg-line @xl:grid-cols-2 @5xl:grid-cols-4">
              <Tile
                label="Volatility"
                value={pct(risk.volatility_pct)}
                note={
                  risk.benchmark_volatility_pct != null
                    ? `A year, from daily moves. ${risk.benchmark_name}: ${pct(risk.benchmark_volatility_pct)}.`
                    : "A year, from daily moves."
                }
              />
              <Tile
                label="Deepest fall from a peak"
                value={pct(risk.max_drawdown.pct)}
                note={
                  recoveryText(risk) +
                  (risk.benchmark_max_drawdown_pct != null
                    ? ` ${risk.benchmark_name}: ${pct(risk.benchmark_max_drawdown_pct)}.`
                    : "")
                }
              />
              <Tile
                label="Below its peak today"
                value={pct(risk.current_drawdown_pct)}
                note={
                  risk.worst_day_pct != null
                    ? `Worst single day: ${pct(risk.worst_day_pct)} on ${fmtDate(risk.worst_day_date)}.`
                    : ""
                }
              />
              <Tile
                label={`Beta vs ${risk.benchmark_name}`}
                value={risk.beta != null ? risk.beta.toFixed(2) : "-"}
                note={betaText(risk)}
              />
            </div>

            {lines.length > 0 && (
              <div className="mt-6 border border-line bg-surface p-5">
                <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                  <p className="label-caps">Distance below the highest close so far</p>
                  <p className="num text-xs text-faint">
                    {fmtDate(risk.from_date)} to {fmtDate(risk.to_date)}
                  </p>
                </div>
                <TimeSeriesChart
                  lines={lines}
                  height={200}
                  valueFormatter={(v) => `${v.toFixed(1)}%`}
                />
                <p className="mt-2 text-xs text-faint">
                  0% means the price is at its highest close of the period.
                </p>
              </div>
            )}

            <p className="mt-4 text-xs leading-relaxed text-faint">
              Computed from {risk.bars_used} stored trading days. Past swings describe the
              past; they do not predict the future.
            </p>
          </>
        )}
      </DataState>
    </CollapsibleSection>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="bg-surface p-5">
      <p className="label-caps">{label}</p>
      <p className="num mt-1.5 text-2xl font-medium">{value}</p>
      {note && <p className="mt-2 text-xs leading-relaxed text-muted">{note}</p>}
    </div>
  );
}
