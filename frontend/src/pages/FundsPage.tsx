import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { useFunds } from "@/lib/hooks";
import type { FundSummary } from "@/lib/types";
import { DataState } from "@/components/data/DataState";
import { HeatCell, heatScale } from "@/components/data/HeatCell";
import { SectionHeader } from "@/components/data/SectionHeader";
import { fmtDate, fmtPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * FundsPage: the curated mutual-fund catalog, laid out as a returns board.
 * Funds are grouped by category (a fund is only comparable with its own
 * kind), and each return is a heat tile whose tint is scaled within its
 * column, so the strong and weak windows of every scheme are visible at a
 * glance. Official AMFI daily NAVs; sorting is server-side and applies
 * inside each category. 1Y/3Y are annualised (CAGR); a "-" window means the
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

const WINDOWS = [
  { key: "return_1m", label: "1M", pick: (f: FundSummary) => f.return_1m_pct },
  { key: "return_3m", label: "3M", pick: (f: FundSummary) => f.return_3m_pct },
  { key: "return_6m", label: "6M", pick: (f: FundSummary) => f.return_6m_pct },
  { key: "return_1y", label: "1Y", pick: (f: FundSummary) => f.return_1y_pct },
  { key: "return_3y", label: "3Y", pick: (f: FundSummary) => f.return_3y_pct },
] as const;

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export default function FundsPage() {
  const [sort, setSort] = React.useState<SortKey>("return_1y");
  const [direction, setDirection] = React.useState<"asc" | "desc">("desc");
  const query = useFunds(sort, direction);
  const funds = query.data;
  const items = funds?.items ?? [];

  const onSort = (key: SortKey) => {
    if (key === sort) {
      setDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSort(key);
      setDirection(key === "name" ? "asc" : "desc");
    }
  };

  // Group by category, keeping the server's order inside each group.
  const groups = React.useMemo(() => {
    const map = new Map<string, FundSummary[]>();
    for (const f of items) {
      const key = f.category ?? "Uncategorised";
      const list = map.get(key);
      if (list) list.push(f);
      else map.set(key, [f]);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [items]);

  // One tint scale per column, across the whole board.
  const scales = WINDOWS.map((w) => heatScale(items.map(w.pick)));
  const navDate = items.find((f) => f.nav_date)?.nav_date ?? null;

  const sortButton = (key: SortKey, label: string) => {
    const active = sort === key;
    return (
      <button
        type="button"
        onClick={() => onSort(key)}
        title={`Sort by ${label}`}
        className={cn(
          "label-caps inline-flex cursor-pointer items-center gap-1 transition-colors hover:text-foreground",
          active && "text-foreground",
        )}
      >
        {label}
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
    );
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 md:px-6">
      <SectionHeader
        kicker="Mutual funds"
        title="Returns board"
        aside={
          funds ? (
            <p className="num text-xs text-muted">
              {funds.total} schemes · {groups.length} categories
              {navDate ? ` · NAV ${fmtDate(navDate)}` : ""}
            </p>
          ) : undefined
        }
      />
      <p className="max-w-2xl text-sm leading-relaxed text-muted">
        Major schemes grouped by category, priced from the official AMFI daily NAV file.
        The deeper the tint, the larger the move within that column. 1Y and 3Y are
        annualised.
      </p>

      <div className="mt-6">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          empty={Boolean(funds) && funds?.total === 0}
          emptyTitle="No funds catalogued yet"
          emptyMessage="The fund catalog fills in when ingestion runs. Nothing is invented in the meantime."
        >
          {items.length > 0 && (
            <div className="overflow-x-auto border border-line bg-surface">
              <table className="w-full min-w-[860px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-line">
                    <th scope="col" className="px-5 py-3">{sortButton("name", "Scheme")}</th>
                    <th scope="col" className="px-3 py-3 text-right">{sortButton("latest_nav", "NAV")}</th>
                    {WINDOWS.map((w) => (
                      <th
                        key={w.key}
                        scope="col"
                        aria-sort={
                          sort === w.key ? (direction === "asc" ? "ascending" : "descending") : "none"
                        }
                        className="w-24 px-1 py-3 text-right"
                      >
                        <span className="pr-2">{sortButton(w.key, w.label)}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                {groups.map(([category, list]) => (
                  <tbody key={category}>
                    <tr className="border-b border-line bg-surface-2">
                      <th scope="colgroup" colSpan={2} className="px-5 py-2 text-left">
                        <span className="text-xs font-semibold text-foreground">{category}</span>
                        <span className="num ml-2 text-xs font-normal text-faint">
                          {list.length} {list.length === 1 ? "scheme" : "schemes"}
                        </span>
                      </th>
                      {WINDOWS.map((w) => {
                        const med = median(
                          list.map(w.pick).filter((v): v is number => v != null),
                        );
                        return (
                          <td
                            key={w.key}
                            className="num px-3 py-2 text-right text-xs text-muted"
                            title={`Category median, ${w.label}`}
                          >
                            {med == null ? "" : `med ${med >= 0 ? "+" : ""}${med.toFixed(1)}%`}
                          </td>
                        );
                      })}
                    </tr>
                    {list.map((fund) => (
                      <tr key={fund.id} className="border-b border-line last:border-b-0">
                        <td className="px-5 py-2">
                          <Link to={`/funds/${fund.id}`} className="group block">
                            <span className="block max-w-96 truncate text-sm font-medium group-hover:text-cobalt group-hover:underline dark:group-hover:text-cobalt-strong">
                              {fund.name}
                            </span>
                            <span className="block text-xs text-faint">
                              {fund.plan}
                              {fund.option ? ` · ${fund.option}` : ""}
                            </span>
                          </Link>
                        </td>
                        <td className="num px-3 py-2 text-right text-sm">
                          {fund.latest_nav != null ? fmtPrice(fund.latest_nav) : "-"}
                        </td>
                        {WINDOWS.map((w, i) => (
                          <td key={w.key} className="p-0.5">
                            <HeatCell value={w.pick(fund)} scale={scales[i]} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                ))}
              </table>
            </div>
          )}
        </DataState>
      </div>

      <p className="mt-4 max-w-3xl text-xs leading-relaxed text-faint">
        NAVs are from AMFI (official, previous business day). "-" means the stored history
        does not cover that window yet. Past performance is not indicative of future
        results. Not investment advice.
      </p>
    </div>
  );
}
