import { useQuarterlyTrend } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { fmtMarketCap } from "@/lib/format";
import type { QuarterRow, QuarterlyTrendResponse } from "@/lib/types";

/**
 * QuarterlyTrend: is the business speeding up or slowing down right now?
 * Each stored quarter beside the same quarter one year earlier, newest
 * first. Computed by the backend's /quarterly-trend endpoint; a change that
 * has no year-earlier quarter to compare with shows "-".
 */

/** "Q2 FY27" for a quarter ending 30 September 2026 (fiscal year ends March). */
export function quarterLabel(periodEnd: string): string {
  const d = new Date(periodEnd);
  const month = d.getUTCMonth() + 1;
  const fy = month >= 4 ? d.getUTCFullYear() + 1 : d.getUTCFullYear();
  const quarter = month >= 4 ? Math.ceil((month - 3) / 3) : 4;
  return `Q${quarter} FY${String(fy).slice(2)}`;
}

function signed(value: number | null, unit: string): string {
  if (value == null) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}${unit}`;
}

export function quarterlyHeadline(trend: QuarterlyTrendResponse | undefined): string | null {
  const latest = trend?.quarters.at(-1);
  if (!trend || !latest || latest.revenue_yoy_pct == null) return null;
  const label = quarterLabel(latest.period_end);
  const sales =
    latest.revenue_yoy_pct >= 0
      ? `Sales grew ${latest.revenue_yoy_pct.toFixed(1)}%`
      : `Sales fell ${Math.abs(latest.revenue_yoy_pct).toFixed(1)}%`;
  let profit = "";
  if (latest.net_income_yoy_pct != null) {
    profit =
      latest.net_income_yoy_pct >= 0
        ? ` and profit grew ${latest.net_income_yoy_pct.toFixed(1)}%`
        : ` and profit fell ${Math.abs(latest.net_income_yoy_pct).toFixed(1)}%`;
  }
  const pace =
    trend.momentum === "faster"
      ? " Sales growth is faster than in the quarter before."
      : trend.momentum === "slower"
        ? " Sales growth is slower than in the quarter before."
        : "";
  return `${sales}${profit} in ${label} against the same quarter last year.${pace}`;
}

export function QuarterlyTrend({ symbol }: { symbol: string }) {
  const query = useQuarterlyTrend(symbol);
  const trend = query.data;
  const rows: QuarterRow[] = trend ? [...trend.quarters].reverse() : [];
  const headline = quarterlyHeadline(trend);
  const maxRevenue = Math.max(0, ...rows.map((r) => r.revenue ?? 0));

  return (
    <div className="border border-line bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-3">
        <p className="label-caps">Quarter by quarter</p>
        <p className="text-xs text-faint">Change is against the same quarter last year</p>
      </div>
      <div className="p-5">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          insufficient={trend?.insufficient_data || undefined}
          insufficientTitle="No quarterly results stored yet"
          insufficientMessage="Quarterly figures appear here after the next data refresh. Nothing is estimated."
          compact
        >
          {trend && rows.length > 0 && (
            <>
              {headline ? (
                <p className="mb-4 max-w-2xl text-sm font-medium leading-relaxed">{headline}</p>
              ) : (
                <p className="mb-4 max-w-2xl text-xs leading-relaxed text-muted">
                  The same quarter last year is not stored for the latest quarter, so no
                  year-on-year change is shown for it.
                </p>
              )}
              <div className="overflow-x-auto">
                <table className="num w-full min-w-[620px] text-right text-xs">
                  <thead>
                    <tr className="border-b border-line text-faint">
                      <th className="py-2 text-left font-medium">Quarter</th>
                      <th className="py-2 pl-4 text-left font-medium">Sales</th>
                      <th className="py-2 font-medium">Change</th>
                      <th className="py-2 font-medium">Net profit</th>
                      <th className="py-2 font-medium">Change</th>
                      <th className="py-2 font-medium">Net margin</th>
                      <th className="py-2 font-medium">Change</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {rows.map((r) => (
                      <tr key={r.period_end}>
                        <td className="py-2.5 text-left font-medium">
                          {quarterLabel(r.period_end)}
                        </td>
                        <td className="py-2.5 pl-4">
                          <span className="flex items-center gap-3">
                            <span className="hidden h-1.5 w-24 bg-line sm:block">
                              {r.revenue != null && maxRevenue > 0 && (
                                <span
                                  className="block h-full bg-cobalt"
                                  style={{ width: `${(r.revenue / maxRevenue) * 100}%` }}
                                />
                              )}
                            </span>
                            <span>{fmtMarketCap(r.revenue)}</span>
                          </span>
                        </td>
                        <td className="py-2.5">{signed(r.revenue_yoy_pct, "%")}</td>
                        <td className="py-2.5">{fmtMarketCap(r.net_income)}</td>
                        <td className="py-2.5">{signed(r.net_income_yoy_pct, "%")}</td>
                        <td className="py-2.5">
                          {r.net_margin_pct != null ? `${r.net_margin_pct.toFixed(1)}%` : "-"}
                        </td>
                        <td className="py-2.5">{signed(r.net_margin_yoy_pts, " pts")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-4 text-xs leading-relaxed text-faint">
                A dash means the same quarter last year is not stored, or it was a loss, so
                a percentage change would be misleading.
                {trend.revenue_growth_streak >= 2
                  ? ` Sales have been above the year-earlier quarter for ${trend.revenue_growth_streak} quarters in a row.`
                  : ""}
              </p>
            </>
          )}
        </DataState>
      </div>
    </div>
  );
}
