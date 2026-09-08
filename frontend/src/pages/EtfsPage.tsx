import { Link } from "react-router-dom";

import { useEtfs } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { SectionHeader } from "@/components/data/SectionHeader";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * EtfsPage: the ETF catalog (Plan 9 slice). Curated exchange-traded funds
 * with the latest quote and one-year return from stored daily bars. Rows
 * link to the standard research page - ETFs reuse the equity price pipeline
 * and never mix into the equity screener or stock list.
 */
export default function EtfsPage() {
  const query = useEtfs();
  const etfs = query.data;

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <SectionHeader index="03" kicker="Discovery" title="ETFs" />
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
        Exchange-traded funds tracked from the same daily price pipeline as
        stocks. Prices are daily close data; a missing figure means the bar
        is not stored yet and is never estimated.
      </p>

      <div className="mt-8">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          empty={Boolean(etfs) && etfs?.total === 0}
          emptyTitle="No ETFs catalogued yet"
          emptyMessage="The ETF catalog fills in when ingestion runs. Nothing is invented in the meantime."
        >
          {etfs && etfs.total > 0 && (
            <div className="border border-line bg-surface">
              <div className="flex items-baseline justify-between border-b border-line px-5 py-3">
                <p className="label-caps">Catalogued ETFs</p>
                <p className="num text-xs text-faint">{etfs.total} funds</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-left">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="px-5 py-3 label-caps font-medium">Fund</th>
                      <th className="px-3 py-3 label-caps text-right font-medium">Price</th>
                      <th className="px-3 py-3 label-caps text-right font-medium">1D</th>
                      <th className="px-5 py-3 label-caps text-right font-medium">1Y</th>
                    </tr>
                  </thead>
                  <tbody>
                    {etfs.items.map((etf) => (
                      <tr key={etf.symbol} className="border-b border-line last:border-b-0">
                        <td className="px-5 py-3">
                          <Link
                            to={`/stocks/${encodeURIComponent(etf.symbol)}`}
                            className="group"
                          >
                            <span className="num block text-sm font-semibold group-hover:text-cobalt group-hover:underline dark:group-hover:text-cobalt-strong">
                              {etf.symbol}
                            </span>
                            <span className="block max-w-72 truncate text-xs text-muted">
                              {etf.name}
                            </span>
                          </Link>
                        </td>
                        <td className="num px-3 py-3 text-right text-sm">
                          {etf.last_price != null ? fmtPrice(etf.last_price) : "-"}
                        </td>
                        <td
                          className={cn(
                            "num px-3 py-3 text-right text-sm font-medium",
                            etf.change_pct == null
                              ? "text-faint"
                              : etf.change_pct > 0
                                ? "text-band-positive"
                                : etf.change_pct < 0
                                  ? "text-band-weak"
                                  : "text-muted",
                          )}
                        >
                          {fmtSignedPct(etf.change_pct)}
                        </td>
                        <td
                          className={cn(
                            "num px-5 py-3 text-right text-sm font-medium",
                            etf.return_1y_pct == null
                              ? "text-faint"
                              : etf.return_1y_pct >= 0
                                ? "text-band-positive"
                                : "text-band-weak",
                          )}
                        >
                          {fmtSignedPct(etf.return_1y_pct)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="border-t border-line px-5 py-3 text-xs text-faint">
                "-" means the figure is not stored yet. Daily close data, as of
                each fund's latest stored bar. Not investment advice.
              </p>
            </div>
          )}
        </DataState>
      </div>
    </div>
  );
}
