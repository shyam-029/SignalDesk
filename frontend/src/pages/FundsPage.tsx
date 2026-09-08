import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { useFunds } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { SectionHeader } from "@/components/data/SectionHeader";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * FundsPage: the curated mutual-fund catalog (Plan 8 slice). Official AMFI
 * daily NAVs; every return column and the category sort server-side, in
 * both directions. 1y/3y are annualised (CAGR); a "-" window means the
 * stored history does not cover it yet and is never estimated.
 */

type SortKey =
  | "category"
  | "name"
  | "latest_nav"
  | "return_1m"
  | "return_3m"
  | "return_6m"
  | "return_1y"
  | "return_3y";

const COLUMNS: Array<{ key: SortKey; label: string; numeric?: boolean }> = [
  { key: "name", label: "Scheme" },
  { key: "category", label: "Category" },
  { key: "latest_nav", label: "NAV", numeric: true },
  { key: "return_1m", label: "1M", numeric: true },
  { key: "return_3m", label: "3M", numeric: true },
  { key: "return_6m", label: "6M", numeric: true },
  { key: "return_1y", label: "1Y", numeric: true },
  { key: "return_3y", label: "3Y", numeric: true },
];

export default function FundsPage() {
  const [sort, setSort] = React.useState<SortKey>("name");
  const [direction, setDirection] = React.useState<"asc" | "desc">("asc");
  const query = useFunds(sort, direction);
  const funds = query.data;

  const onSort = (key: SortKey) => {
    if (key === sort) {
      setDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSort(key);
      setDirection("asc");
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <SectionHeader index="03" kicker="Discovery" title="Mutual funds" />
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
        A curated set of major schemes across categories, priced from the
        official AMFI daily NAV file. Every column sorts both directions; 1Y
        and 3Y are annualised. A window the stored history does not cover yet
        shows "-" and is never estimated.
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
                <table className="w-full min-w-[880px] border-collapse text-left">
                  <thead>
                    <tr className="border-b border-line">
                      {COLUMNS.map((col) => {
                        const active = sort === col.key;
                        return (
                          <th
                            key={col.key}
                            scope="col"
                            aria-sort={
                              active
                                ? direction === "asc"
                                  ? "ascending"
                                  : "descending"
                                : "none"
                            }
                            className={cn(
                              "px-3 py-3",
                              col.key === "name" && "pl-5",
                              col.numeric ? "text-right" : "text-left",
                            )}
                          >
                            <button
                              type="button"
                              onClick={() => onSort(col.key)}
                              className={cn(
                                "label-caps inline-flex cursor-pointer items-center gap-1 transition-colors hover:text-foreground",
                                active && "text-foreground",
                              )}
                              title={`Sort by ${col.label}`}
                            >
                              {col.label}
                              {active ? (
                                direction === "asc" ? (
                                  <ArrowUp className="size-3" aria-hidden />
                                ) : (
                                  <ArrowDown className="size-3" aria-hidden />
                                )
                              ) : (
                                <ArrowUpDown className="size-3 opacity-40" aria-hidden />
                              )}
                            </button>
                          </th>
                        );
                      })}
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
                        {(["1m", "3m", "6m", "1y", "3y"] as const).map((w) => {
                          const value =
                            w === "1m"
                              ? fund.return_1m_pct
                              : w === "3m"
                                ? fund.return_3m_pct
                                : w === "6m"
                                  ? fund.return_6m_pct
                                  : w === "1y"
                                    ? fund.return_1y_pct
                                    : fund.return_3y_pct;
                          return (
                            <td
                              key={w}
                              className={cn(
                                "num px-3 py-3 text-right text-sm font-medium",
                                value == null ? "text-faint" : value >= 0 ? "text-band-positive" : "text-band-weak",
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
