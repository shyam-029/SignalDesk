import { useQuality } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { InfoDot } from "@/components/data/InfoDot";
import type { QualityResponse } from "@/lib/types";

/**
 * QualityBreakdown: return on equity split into its three levers (profit
 * margin, asset turnover, leverage) for each stored fiscal year, so the
 * profitability score above it is explained rather than only stated.
 * Computed by the backend's /quality endpoint from the stored income
 * statements and balance sheets. A year missing an input shows "-".
 */

const DRIVER_LABEL: Record<string, string> = {
  margin: "profit margin",
  turnover: "asset turnover",
  leverage: "leverage",
};

/** Plain-word help shown behind the "?" beside each column name. */
const HELP = {
  margin: { label: "Profit margin", short: "Profit kept from each rupee of sales." },
  turnover: { label: "Asset turnover", short: "Sales made per rupee of assets." },
  leverage: {
    label: "Leverage",
    short: "Assets per rupee of shareholder money. Higher means more borrowing.",
  },
  roe: {
    label: "Return on equity",
    short: "Profit earned per rupee of shareholder money. It is the other three multiplied together.",
  },
};

function Head({ help }: { help: { label: string; short: string } }) {
  return (
    <th className="py-2 font-medium">
      <span className="inline-flex items-center justify-end gap-1.5">
        {help.label}
        <InfoDot info={help} glyph="?" className="size-3.5" />
      </span>
    </th>
  );
}

const REASONS: Record<string, string> = {
  non_applicable_financial:
    "For banks and other financial companies, sales over assets does not describe how the return is earned.",
  missing_balance_sheet: "No balance sheet is stored for this stock yet.",
  missing_inputs:
    "The stored years are each missing a figure this breakdown needs, or have negative equity.",
};

/** Indian fiscal year label for a period end ("FY2026" for 31 March 2026). */
function fiscalYear(periodEnd: string): string {
  const d = new Date(periodEnd);
  const year = d.getUTCMonth() >= 3 ? d.getUTCFullYear() + 1 : d.getUTCFullYear();
  return `FY${year}`;
}

function verdict(q: QualityResponse): string | null {
  if (q.driver == null || q.roe_change_pts == null || !q.from_period || !q.to_period) {
    return null;
  }
  const span = `between ${fiscalYear(q.from_period)} and ${fiscalYear(q.to_period)}`;
  const pts = Math.abs(q.roe_change_pts).toFixed(1);
  if (Math.abs(q.roe_change_pts) < 0.5) {
    return `Return on equity was nearly unchanged ${span}.`;
  }
  const direction = q.roe_change_pts > 0 ? "rose" : "fell";
  return `Return on equity ${direction} ${pts} points ${span}, mostly because of ${DRIVER_LABEL[q.driver]}.`;
}

export function QualityBreakdown({ symbol }: { symbol: string }) {
  const query = useQuality(symbol);
  const q = query.data;
  const headline = q ? verdict(q) : null;

  return (
    <div className="border border-line bg-surface">
      <div className="border-b border-line px-5 py-3">
        <p className="label-caps">What drives return on equity</p>
      </div>
      <div className="p-5">
        <DataState loading={query.isLoading} error={query.error} onRetry={query.refetch} compact>
          {q && q.status !== "available" && (
            <div>
              <p className="num text-2xl font-medium text-faint">-</p>
              <p className="mt-2 max-w-xl text-xs leading-relaxed text-muted">
                {q.status === "not_applicable" ? "Not applicable. " : "Not computable. "}
                {REASONS[q.reason ?? ""] ?? "The stored data does not support this breakdown."}{" "}
                Nothing is estimated.
              </p>
            </div>
          )}

          {q && q.status === "available" && (
            <>
              {headline && (
                <p className="mb-4 max-w-2xl text-sm font-medium leading-relaxed">{headline}</p>
              )}
              <div className="overflow-x-auto">
                <table className="num w-full min-w-[520px] text-right text-xs">
                  <thead>
                    <tr className="border-b border-line text-faint">
                      <th className="py-2 text-left font-medium">Year</th>
                      <Head help={HELP.margin} />
                      <Head help={HELP.turnover} />
                      <Head help={HELP.leverage} />
                      <Head help={HELP.roe} />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {q.years.map((y) => (
                      <tr key={y.period_end}>
                        <td className="py-2.5 text-left font-medium">{fiscalYear(y.period_end)}</td>
                        <td className="py-2.5">
                          {y.net_margin_pct != null ? `${y.net_margin_pct.toFixed(1)}%` : "-"}
                        </td>
                        <td className="py-2.5">
                          {y.asset_turnover != null ? `${y.asset_turnover.toFixed(2)}x` : "-"}
                        </td>
                        <td className="py-2.5">
                          {y.equity_multiplier != null ? `${y.equity_multiplier.toFixed(2)}x` : "-"}
                        </td>
                        <td className="py-2.5 font-semibold">
                          {y.roe_pct != null ? `${y.roe_pct.toFixed(1)}%` : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-4 text-xs leading-relaxed text-faint">
                The three multiplied together give return on equity. Year-end balances are
                used, so figures can differ slightly from ratios based on yearly averages.
              </p>
            </>
          )}

          {q && !q.cash_flow_available && (
            <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-faint">
              Checks that need the cash-flow statement (profit backed by cash, the Piotroski
              score) are not shown: cash-flow statements are not stored yet.
            </p>
          )}
        </DataState>
      </div>
    </div>
  );
}
