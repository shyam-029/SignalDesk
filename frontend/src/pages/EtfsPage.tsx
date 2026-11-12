import * as React from "react";
import { Link } from "react-router-dom";

import { useEtfs } from "@/lib/hooks";
import type { EtfSummary } from "@/lib/types";
import { DataState } from "@/components/data/DataState";
import { HeatCell, heatScale } from "@/components/data/HeatCell";
import { SectionHeader } from "@/components/data/SectionHeader";
import { fmtDate, fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * EtfsPage: the ETF catalog as a one-year league table. Each fund is a row
 * with a bar that grows right (gain) or left (loss) from a shared zero line,
 * so the whole shelf can be compared without reading a single number; the
 * day's move sits beside it as a heat tile. Rows link to the standard
 * research page: ETFs reuse the equity price pipeline and never mix into the
 * equity screener or stock list. A missing figure is "-" and has no bar.
 */

type SortKey = "return_1y" | "change" | "symbol";

const SORTS: Array<{ key: SortKey; label: string }> = [
  { key: "return_1y", label: "1Y return" },
  { key: "change", label: "Today" },
  { key: "symbol", label: "A to Z" },
];

function sortEtfs(items: EtfSummary[], key: SortKey): EtfSummary[] {
  const desc = (a: number | null, b: number | null) =>
    a == null ? (b == null ? 0 : 1) : b == null ? -1 : b - a; // nulls last
  return [...items].sort((a, b) =>
    key === "symbol"
      ? a.symbol.localeCompare(b.symbol)
      : key === "change"
        ? desc(a.change_pct, b.change_pct)
        : desc(a.return_1y_pct, b.return_1y_pct),
  );
}

export default function EtfsPage() {
  const query = useEtfs();
  const etfs = query.data;
  const [sort, setSort] = React.useState<SortKey>("return_1y");

  const items = React.useMemo(() => sortEtfs(etfs?.items ?? [], sort), [etfs, sort]);
  const yearScale = heatScale(items.map((e) => e.return_1y_pct));
  const dayScale = heatScale(items.map((e) => e.change_pct));
  const asOf = items.find((e) => e.as_of)?.as_of ?? null;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 md:px-6">
      <SectionHeader
        kicker="Exchange-traded funds"
        title="One-year league table"
        aside={
          <div className="flex items-center gap-1" role="group" aria-label="Sort ETFs">
            {SORTS.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => setSort(s.key)}
                aria-pressed={sort === s.key}
                className={cn(
                  "border px-2.5 py-1 text-xs font-medium transition-colors",
                  sort === s.key
                    ? "border-cobalt text-foreground"
                    : "border-line text-muted hover:text-foreground",
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
        }
      />
      <p className="max-w-2xl text-sm leading-relaxed text-muted">
        Funds tracked from the same daily price pipeline as stocks. Bars share one zero
        line and one scale, so their lengths compare directly.
        {asOf ? ` Daily close data, latest bar ${fmtDate(asOf)}.` : ""}
      </p>

      <div className="mt-6">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          empty={Boolean(etfs) && etfs?.total === 0}
          emptyTitle="No ETFs catalogued yet"
          emptyMessage="The ETF catalog fills in when ingestion runs. Nothing is invented in the meantime."
        >
          {items.length > 0 && (
            <div className="overflow-x-auto border border-line bg-surface">
              <table className="w-full min-w-[720px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-line">
                    <th scope="col" className="label-caps px-5 py-3">Fund</th>
                    <th scope="col" className="label-caps px-3 py-3 text-right">Price</th>
                    <th scope="col" className="label-caps w-24 px-3 py-3 text-right">Today</th>
                    <th scope="col" className="label-caps px-5 py-3">One year</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((etf) => (
                    <tr key={etf.symbol} className="border-b border-line last:border-b-0 hover:bg-surface-2/50">
                      <td className="px-5 py-2.5">
                        <Link to={`/stocks/${encodeURIComponent(etf.symbol)}`} className="group block">
                          <span className="tkr block text-sm font-semibold group-hover:text-cobalt group-hover:underline dark:group-hover:text-cobalt-strong">
                            {etf.symbol.replace(".NS", "")}
                          </span>
                          <span className="block max-w-72 truncate text-xs text-muted">{etf.name}</span>
                        </Link>
                      </td>
                      <td className="num px-3 py-2.5 text-right text-sm">
                        {etf.last_price != null ? fmtPrice(etf.last_price) : "-"}
                      </td>
                      <td className="p-0.5">
                        <HeatCell value={etf.change_pct} scale={dayScale} />
                      </td>
                      <td className="px-5 py-2.5">
                        <DivergingBar value={etf.return_1y_pct} scale={yearScale} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataState>
      </div>

      <p className="mt-4 max-w-3xl text-xs leading-relaxed text-faint">
        "-" means the figure is not stored yet (a fund needs a year of bars for the
        one-year return). Not investment advice.
      </p>
    </div>
  );
}

/** A bar from a centered zero line: right for a gain, left for a loss. */
function DivergingBar({ value, scale }: { value: number | null; scale: number }) {
  if (value == null) return <span className="num text-sm text-faint">-</span>;
  const half = scale > 0 ? Math.min(50, (Math.abs(value) / scale) * 50) : 0;
  const up = value >= 0;
  return (
    <span className="flex items-center gap-3">
      <span className="relative block h-4 min-w-40 flex-1" aria-hidden>
        <span className="absolute inset-y-0 left-1/2 w-px bg-rule" />
        <span
          className="absolute inset-y-0.5"
          style={{
            background: up ? "var(--up)" : "var(--down)",
            width: `${half}%`,
            left: up ? "50%" : `${50 - half}%`,
          }}
        />
      </span>
      <span className={cn("num w-16 shrink-0 text-right text-sm font-medium", up ? "text-up" : "text-down")}>
        {fmtSignedPct(value)}
      </span>
    </span>
  );
}
