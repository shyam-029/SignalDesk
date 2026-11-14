import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react";

import { useFundCategories, useFunds } from "@/lib/hooks";
import type { FundSummary } from "@/lib/types";
import { DataState } from "@/components/data/DataState";
import { HeatCell, heatScale } from "@/components/data/HeatCell";
import { SectionHeader } from "@/components/data/SectionHeader";
import { fmtDate, fmtPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * FundsPage: the mutual-fund returns board. With the funds database it lists
 * every direct growth plan and ETF in AMFI's daily file (about 1,900), so
 * the board is filtered (asset type, category, name search) and paged on the
 * server; each return is a heat tile tinted within its column on the page.
 * 1Y and longer are annualised (CAGR). "Rank" is the fund's place by one-year
 * return within its category. A "-" means the stored history does not cover
 * that window; nothing is estimated. Without the funds database the older
 * curated list is shown with the same board.
 */

type SortKey =
  | "category"
  | "name"
  | "latest_nav"
  | "return_1m"
  | "return_3m"
  | "return_6m"
  | "return_1y"
  | "return_3y"
  | "return_5y";

const WINDOWS = [
  { key: "return_1m", label: "1M", pick: (f: FundSummary) => f.return_1m_pct },
  { key: "return_3m", label: "3M", pick: (f: FundSummary) => f.return_3m_pct },
  { key: "return_1y", label: "1Y", pick: (f: FundSummary) => f.return_1y_pct },
  { key: "return_3y", label: "3Y", pick: (f: FundSummary) => f.return_3y_pct },
  { key: "return_5y", label: "5Y", pick: (f: FundSummary) => f.return_5y_pct ?? null },
] as const;

const GROUPS = [
  { key: "", label: "All" },
  { key: "equity", label: "Equity" },
  { key: "hybrid", label: "Hybrid" },
  { key: "debt", label: "Debt" },
  { key: "other", label: "Other" },
] as const;

const PAGE = 50;

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function FundsPage() {
  const [sort, setSort] = React.useState<SortKey>("return_1y");
  const [direction, setDirection] = React.useState<"asc" | "desc">("desc");
  const [group, setGroup] = React.useState<string>("equity");
  const [category, setCategory] = React.useState<string>("");
  const [search, setSearch] = React.useState("");
  const [page, setPage] = React.useState(0);
  const q = useDebounced(search.trim());

  // Any filter change starts again from the first page.
  React.useEffect(() => setPage(0), [group, category, q, sort, direction]);

  const query = useFunds(sort, direction, category || undefined, {
    assetGroup: group || undefined,
    q: q || undefined,
    limit: PAGE,
    offset: page * PAGE,
  });
  const categories = useFundCategories();
  const funds = query.data;
  const items = funds?.items ?? [];
  const full = funds?.source === "funds_db";
  const total = funds?.total ?? 0;

  const categoryOptions = React.useMemo(() => {
    const rows = categories.data?.items ?? [];
    return rows
      .filter((c) => c.category && (!group || c.asset_group === group))
      .sort((a, b) => (a.category ?? "").localeCompare(b.category ?? ""));
  }, [categories.data, group]);

  const onSort = (key: SortKey) => {
    if (key === sort) {
      setDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSort(key);
      setDirection(key === "name" || key === "category" ? "asc" : "desc");
    }
  };

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
              {total.toLocaleString("en-IN")} {total === 1 ? "fund" : "funds"}
              {navDate ? ` · NAV ${fmtDate(navDate)}` : ""}
            </p>
          ) : undefined
        }
      />
      <p className="max-w-2xl text-sm leading-relaxed text-muted">
        {full
          ? "Every direct growth plan and ETF in AMFI's daily file, "
          : "Major schemes, "}
        priced from the official AMFI daily NAV. The deeper the tint, the larger the move within
        that column. 1Y and longer are annualised; rank is by one-year return within the category.
      </p>

      {full && (
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <div role="tablist" aria-label="Asset type" className="flex flex-wrap gap-1">
            {GROUPS.map((g) => (
              <button
                key={g.key}
                type="button"
                role="tab"
                aria-selected={group === g.key}
                onClick={() => {
                  setGroup(g.key);
                  setCategory("");
                }}
                className={cn(
                  "border px-3 py-1 text-xs font-medium transition-colors",
                  group === g.key
                    ? "border-cobalt bg-surface-2 text-foreground"
                    : "border-line text-muted hover:text-foreground",
                )}
              >
                {g.label}
              </button>
            ))}
          </div>
          <label className="sr-only" htmlFor="fund-category">
            Category
          </label>
          <select
            id="fund-category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="min-w-0 max-w-full border border-line bg-surface px-2 py-1 text-xs"
          >
            <option value="">All categories</option>
            {categoryOptions.map((c) => (
              <option key={`${c.asset_group}-${c.category}`} value={c.category ?? ""}>
                {c.category} ({c.count})
              </option>
            ))}
          </select>
          <div className="relative min-w-0 flex-1 sm:max-w-xs">
            <Search
              className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-faint"
              aria-hidden
            />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search funds"
              aria-label="Search funds by name"
              className="w-full border border-line bg-surface py-1 pl-7 pr-2 text-xs"
            />
          </div>
        </div>
      )}

      <div className="mt-4">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          empty={Boolean(funds) && total === 0}
          emptyTitle={full ? "No funds match" : "No funds catalogued yet"}
          emptyMessage={
            full
              ? "Try another category or search."
              : "The fund catalog fills in when ingestion runs. Nothing is invented in the meantime."
          }
        >
          {items.length > 0 && (
            <div
              className={cn(
                "overflow-x-auto border border-line bg-surface transition-opacity",
                query.isPlaceholderData && "opacity-60",
              )}
            >
              <table className="w-full min-w-[920px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-line">
                    <th scope="col" className="px-5 py-3">{sortButton("name", "Fund")}</th>
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
                    {full && (
                      <th scope="col" className="w-20 px-3 py-3 text-right">
                        <span className="label-caps">Rank</span>
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {items.map((fund) => (
                    <tr key={fund.id} className="border-b border-line last:border-b-0">
                      <td className="px-5 py-2">
                        <Link to={`/funds/${fund.id}`} className="group block">
                          <span className="block max-w-[26rem] truncate text-sm font-medium group-hover:text-cobalt group-hover:underline dark:group-hover:text-cobalt-strong">
                            {fund.name}
                          </span>
                          <span className="block max-w-[26rem] truncate text-xs text-faint">
                            {[fund.fund_house, fund.category, fund.kind === "etf" ? "ETF" : null]
                              .filter(Boolean)
                              .join(" · ") || [fund.plan, fund.option].filter(Boolean).join(" · ")}
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
                      {full && (
                        <td className="num px-3 py-2 text-right text-xs text-muted">
                          {fund.category_rank != null && fund.category_size != null
                            ? `${fund.category_rank} / ${fund.category_size}`
                            : "-"}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataState>
      </div>

      {full && total > PAGE && (
        <div className="mt-3 flex items-center justify-between gap-3 text-xs text-muted">
          <span className="num">
            {page * PAGE + 1}-{Math.min(total, (page + 1) * PAGE)} of {total.toLocaleString("en-IN")}
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              className="border border-line px-3 py-1 disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={(page + 1) * PAGE >= total}
              onClick={() => setPage((p) => p + 1)}
              className="border border-line px-3 py-1 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}

      <p className="mt-4 max-w-3xl text-xs leading-relaxed text-faint">
        NAVs are from AMFI (official, previous business day); history before tracking began is
        from mfapi.in. "-" means the stored history does not cover that window. Past performance
        is not indicative of future results. Not investment advice.
      </p>
    </div>
  );
}
