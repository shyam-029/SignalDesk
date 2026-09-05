import * as React from "react";

import { useFinancialsHistory } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { InfoDot } from "@/components/data/InfoDot";
import { TimeSeriesChart, type TimeSeriesLine } from "@/components/chart/TimeSeriesChart";
import { fmtDate } from "@/lib/format";

/**
 * FinancialsHistoryChart: multi-year annual income statements from the
 * backend's /financials/history endpoint (Part D). Revenue and net income
 * are charted in crore of rupees (unit scaling for display only; the values
 * themselves are backend data), operating and net margin in percent. Periods
 * a provider did not supply leave a visible gap in the line: missing history
 * is never interpolated. Rows are sorted by period end for charting only.
 */
export function FinancialsHistoryChart({ symbol }: { symbol: string }) {
  const query = useFinancialsHistory(symbol, "annual");
  const periods = React.useMemo(
    () =>
      [...(query.data?.items ?? [])].sort(
        (a, b) => new Date(a.period_end).getTime() - new Date(b.period_end).getTime(),
      ),
    [query.data],
  );

  const hasRevenue = periods.some((p) => p.revenue != null);
  const hasNetIncome = periods.some((p) => p.net_income != null);
  const hasMargins = periods.some((p) => p.operating_margin != null || p.net_margin != null);

  const moneyLines = React.useMemo<TimeSeriesLine[]>(
    () => [
      {
        key: "revenue",
        label: "Revenue",
        color: "--cobalt",
        data: periods.map((p) => ({ time: p.period_end, value: p.revenue == null ? null : p.revenue / 1e7 })),
        histogram: true,
      },
      {
        key: "net_income",
        label: "Net income",
        color: "--accent-jade",
        data: periods.map((p) => ({ time: p.period_end, value: p.net_income == null ? null : p.net_income / 1e7 })),
        histogram: true,
      },
    ],
    [periods],
  );

  const marginLines = React.useMemo<TimeSeriesLine[]>(
    () => [
      {
        key: "operating_margin",
        label: "Operating margin",
        color: "--accent-amber",
        data: periods.map((p) => ({
          time: p.period_end,
          value: p.operating_margin == null ? null : p.operating_margin * 100,
        })),
        points: true,
      },
      {
        key: "net_margin",
        label: "Net margin",
        color: "--accent-teal",
        data: periods.map((p) => ({
          time: p.period_end,
          value: p.net_margin == null ? null : p.net_margin * 100,
        })),
        points: true,
      },
    ],
    [periods],
  );

  const latest = [...periods].reverse().find(
    (p) => p.revenue != null || p.net_income != null || p.net_margin != null,
  );
  const insufficient = Boolean(query.data?.insufficient_data) || periods.length === 0;

  return (
    <div className="border border-line bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-3">
        <p className="label-caps">Historical financials · annual</p>
        <p className="num text-xs text-faint">
          {periods.length > 0
            ? `${fmtDate(periods[0].period_end)} to ${fmtDate(periods.at(-1)!.period_end)} · ${periods.length} period${periods.length === 1 ? "" : "s"}`
            : ""}
        </p>
      </div>

      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        insufficient={insufficient}
        insufficientTitle="No annual history stored"
        insufficientMessage="Multi-year income statements are ingested per period. Until a period row exists for this stock there is nothing to chart, and nothing is estimated."
        compact
      >
        <div className="grid gap-px bg-line md:grid-cols-2">
          {(hasRevenue || hasNetIncome) && (
            <div className="bg-surface p-5">
              <p className="label-caps mb-3">Revenue and net income (₹ Cr)</p>
              <TimeSeriesChart
                lines={moneyLines}
                height={220}
                valueFormatter={(v) => `${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })} Cr`}
              />
              <p className="num mt-2 text-xs text-faint">
                One bar per reported period · {periods.length} period{periods.length === 1 ? "" : "s"} stored
              </p>
            </div>
          )}
          {hasMargins && (
            <div className="bg-surface p-5">
              <p className="label-caps mb-3 flex items-center gap-1.5">
                Margins
                <InfoDot metric="operating_margin" className="size-3" />
              </p>
              <TimeSeriesChart
                lines={marginLines}
                height={220}
                valueFormatter={(v) => `${v.toFixed(1)}%`}
              />
              <p className="num mt-2 text-xs text-faint">
                Computed by the backend from the same period's figures
              </p>
            </div>
          )}
        </div>

        {latest && (
          <div className="num flex flex-wrap gap-x-6 gap-y-1 border-t border-line px-5 py-3 text-xs text-muted">
            <span className="text-foreground">{fmtDate(latest.period_end)}</span>
            <span>
              Revenue{" "}
              <span className="text-foreground">
                {latest.revenue != null ? crValue(latest.revenue) : "-"}
              </span>
            </span>
            <span>
              Net income{" "}
              <span className="text-foreground">
                {latest.net_income != null ? crValue(latest.net_income) : "-"}
              </span>
            </span>
            <span>
              Op margin{" "}
              <span className="text-foreground">
                {latest.operating_margin != null ? `${(latest.operating_margin * 100).toFixed(1)}%` : "-"}
              </span>
            </span>
            <span>
              Net margin{" "}
              <span className="text-foreground">
                {latest.net_margin != null ? `${(latest.net_margin * 100).toFixed(1)}%` : "-"}
              </span>
            </span>
            <span className="text-faint">source: {latest.source}</span>
          </div>
        )}
      </DataState>
    </div>
  );
}

function crValue(rupees: number): string {
  return `₹${(rupees / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 0 })} Cr`;
}
