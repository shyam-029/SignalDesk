import { Link } from "react-router-dom";

import { useFunds } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { SectionHeader } from "@/components/data/SectionHeader";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * FundsPage: the curated mutual-fund catalog (Plan 8 slice). Official AMFI
 * daily NAVs, windowed returns computed by the backend from stored NAV
 * history. Rows link to the fund detail page; returns show "-" until the
 * stored history covers the window.
 */
export default function FundsPage() {
  const query = useFunds();
  const funds = query.data;

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <SectionHeader index="03" kicker="Discovery" title="Mutual funds" />
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
        A curated set of major schemes across categories, priced from the
        official AMFI daily NAV file. Returns are computed by SignalDesk from
        stored NAV history - windows the history does not cover yet show "-"
        and are never estimated.
      </p>

      <div className="mt-8">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          empty={Boolean(funds) && funds?.total === 0}
          emptyTitle="No funds catalogued yet"
          emptyMessage="The fund catalog fills in when ingestion runs. Nothing is invented in the meantime."
        >
          {funds && funds.total > 0 && (
            <div className="border border-line bg-surface">
              <div className="flex items-baseline justify-between border-b border-line px-5 py-3">
                <p className="label-caps">Curated funds</p>
                <p className="num text-xs text-faint">{funds.total} schemes</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] border-collapse text-left">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="px-5 py-3 label-caps font-medium">Scheme</th>
                      <th className="px-3 py-3 label-caps font-medium">Category</th>
                      <th className="px-3 py-3 label-caps text-right font-medium">NAV</th>
                      <th className="px-3 py-3 label-caps text-right font-medium">1M</th>
                      <th className="px-3 py-3 label-caps text-right font-medium">3M</th>
                      <th className="px-5 py-3 label-caps text-right font-medium">6M</th>
                    </tr>
                  </thead>
                  <tbody>
                    {funds.items.map((fund) => (
                      <tr key={fund.id} className="border-b border-line last:border-b-0">
                        <td className="px-5 py-3">
                          <Link to={`/funds/${fund.id}`} className="group">
                            <span className="block max-w-80 truncate text-sm font-semibold group-hover:text-cobalt group-hover:underline dark:group-hover:text-cobalt-strong">
                              {fund.name}
                            </span>
                            <span className="num block text-xs text-faint">
                              {fund.plan}
                              {fund.option ? ` · ${fund.option}` : ""}
                            </span>
                          </Link>
                        </td>
                        <td className="px-3 py-3 text-xs text-muted">{fund.category ?? "-"}</td>
                        <td className="num px-3 py-3 text-right text-sm">
                          {fund.latest_nav != null ? (
                            <>
                              {fmtPrice(fund.latest_nav)}
                              <span className="ml-1 block text-xs text-faint">
                                {fund.nav_date ?? ""}
                              </span>
                            </>
                          ) : (
                            "-"
                          )}
                        </td>
                        {(["1m", "3m", "6m"] as const).map((w) => {
                          const value =
                            w === "1m"
                              ? fund.return_1m_pct
                              : w === "3m"
                                ? fund.return_3m_pct
                                : fund.return_6m_pct;
                          return (
                            <td
                              key={w}
                              className={cn(
                                "num px-3 py-3 text-right text-sm font-medium last:px-5",
                                value == null
                                  ? "text-faint"
                                  : value >= 0
                                    ? "text-band-positive"
                                    : "text-band-weak",
                              )}
                            >
                              {fmtSignedPct(value)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="border-t border-line px-5 py-3 text-xs text-faint">
                NAVs are from AMFI (official, T-1); history also carries a
                documented fallback backfill. Past performance is not
                indicative of future results. Not investment advice.
              </p>
            </div>
          )}
        </DataState>
      </div>
    </div>
  );
}
