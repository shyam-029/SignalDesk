import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, ArrowUpDown, Search, X } from "lucide-react";

import { useFundCategories, useFunds } from "@/lib/hooks";
import type { FundSummary } from "@/lib/types";
import { DataState } from "@/components/data/DataState";
import { HeatCell, heatScale } from "@/components/data/HeatCell";
import { SectionHeader } from "@/components/data/SectionHeader";
import { RankBar } from "@/components/fund/RankBar";
import { kindLabel } from "@/components/fund/fundFormat";
import { fmtDate, fmtPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * FundsPage: the mutual-fund board. With the funds database it lists every
 * direct growth plan and ETF in AMFI's daily file (about 1,900), so the board
 * is filtered (asset type, category, name search) and paged on the server.
 * Two views share the rows: "Returns" (each return a heat tile tinted within
 * its column on the page) and "Risk and long run" (ten-year and since-launch
 * returns, yearly swing, deepest fall). 1Y and longer are annualised (CAGR).
 * "Rank" is the fund's place by one-year return within its category. A "-"
 * means the stored history does not cover that window; nothing is estimated.
 * Without the funds database the older curated list is shown, returns only.
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
  | "return_5y"
  | "return_10y";

type View = "returns" | "risk";

interface Window {
  key: SortKey;
  label: string;
  pick: (f: FundSummary) => number | null;
}

const RETURN_WINDOWS: Window[] = [
  { key: "return_1m", label: "1M", pick: (f) => f.return_1m_pct },
  { key: "return_3m", label: "3M", pick: (f) => f.return_3m_pct },
  { key: "return_1y", label: "1Y", pick: (f) => f.return_1y_pct },
  { key: "return_3y", label: "3Y", pick: (f) => f.return_3y_pct },
  { key: "return_5y", label: "5Y", pick: (f) => f.return_5y_pct ?? null },
];

const LONG_WINDOWS: Window[] = [
  { key: "return_5y", label: "5Y", pick: (f) => f.return_5y_pct ?? null },
  { key: "return_10y", label: "10Y", pick: (f) => f.return_10y_pct ?? null },
];

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

const tabClass = (active: boolean) =>
  cn(
    "border px-3 py-1 text-xs font-medium transition-colors",
    active
      ? "border-cobalt bg-surface-2 text-foreground"
      : "border-line text-muted hover:text-foreground",
  );

function subline(fund: FundSummary): string {
  return (
    [fund.fund_house, fund.category].filter(Boolean).join(" · ") ||
    [fund.plan, fund.option].filter(Boolean).join(" · ")
  );
}

function KindBadge({ kind }: { kind: FundSummary["kind"] }) {
  const label = kindLabel(kind);
  if (!label) return null;
  return (
    <span className="ml-2 inline-block border border-line px-1 py-px align-middle text-[10px] font-medium uppercase tracking-wide text-muted">
      {label}
    </span>
  );
}

function plainPct(v: number | null | undefined): string {
  return v == null ? "-" : `${v.toFixed(1)}%`;
}

export default function FundsPage() {
  const [sort, setSort] = React.useState<SortKey>("return_1y");
  const [direction, setDirection] = React.useState<"asc" | "desc">("desc");
  const [group, setGroup] = React.useState<string>("equity");
  const [category, setCategory] = React.useState<string>("");
  const [search, setSearch] = React.useState("");
  const [view, setView] = React.useState<View>("returns");
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
  const risk = full && view === "risk";
  const windows = risk ? LONG_WINDOWS : RETURN_WINDOWS;

  const categoryOptions = React.useMemo(() => {
    const rows = categories.data?.items ?? [];
    return rows
      .filter((c) => c.category && (!group || c.asset_group === group))
      .sort((a, b) => (a.category ?? "").localeCompare(b.category ?? ""));
  }, [categories.data, group]);

  const groupCounts = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const c of categories.data?.items ?? []) {
      counts.set(c.asset_group ?? "", (counts.get(c.asset_group ?? "") ?? 0) + c.count);
      counts.set("", (counts.get("") ?? 0) + c.count);
    }
    return counts;
  }, [categories.data]);

  const onSort = (key: SortKey) => {
    if (key === sort) {
      setDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSort(key);
      setDirection(key === "name" || key === "category" ? "asc" : "desc");
    }
  };

  const scales = windows.map((w) => heatScale(items.map(w.pick)));
  // The three figures a phone card shows for the current view.
  const cards: Array<{ label: string; heat: boolean; pick: (f: FundSummary) => number | null }> =
    risk
      ? [
          { label: "10Y", heat: true, pick: (f) => f.return_10y_pct ?? null },
          { label: "Swing", heat: false, pick: (f) => f.volatility_pct ?? null },
          { label: "Fall", heat: false, pick: (f) => f.max_drawdown_pct ?? null },
        ]
      : [
          { label: "1Y", heat: true, pick: (f) => f.return_1y_pct },
          { label: "3Y", heat: true, pick: (f) => f.return_3y_pct },
          { label: "5Y", heat: true, pick: (f) => f.return_5y_pct ?? null },
        ];
  const cardScales = cards.map((c) => (c.heat ? heatScale(items.map(c.pick)) : 0));
  const navDate = items.find((f) => f.nav_date)?.nav_date ?? null;
  const filtered = Boolean(category || q);

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
        title={full ? "Every direct plan, side by side" : "Returns board"}
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
        that column. 1Y and longer are yearly rates; rank is by one-year return within the
        category.
      </p>

      {full && (
        <div className="mt-6 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
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
                  className={tabClass(group === g.key)}
                >
                  {g.label}
                  {groupCounts.has(g.key) && (
                    <span className="num ml-1.5 text-faint">
                      {groupCounts.get(g.key)?.toLocaleString("en-IN")}
                    </span>
                  )}
                </button>
              ))}
            </div>
            <div role="group" aria-label="Columns" className="flex gap-1">
              {(
                [
                  ["returns", "Returns"],
                  ["risk", "Risk and long run"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  aria-pressed={view === key}
                  onClick={() => setView(key)}
                  className={tabClass(view === key)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="sr-only" htmlFor="fund-category">
              Category
            </label>
            <select
              id="fund-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="min-w-0 max-w-full border border-line bg-surface px-2 py-1.5 text-xs"
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
                placeholder="Search by fund or fund house"
                aria-label="Search funds by name"
                className="w-full border border-line bg-surface py-1.5 pl-7 pr-2 text-xs"
              />
            </div>
            {filtered && (
              <button
                type="button"
                onClick={() => {
                  setCategory("");
                  setSearch("");
                }}
                className="inline-flex items-center gap-1 text-xs text-muted hover:text-foreground"
              >
                <X className="size-3" aria-hidden />
                Clear
              </button>
            )}
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
            <div className={cn("transition-opacity", query.isPlaceholderData && "opacity-60")}>
              {/* Phones: one card a fund. */}
              <ul className="border border-line bg-surface md:hidden">
                {items.map((fund) => (
                  <li key={fund.id} className="border-b border-line p-4 last:border-b-0">
                    <div className="flex items-start justify-between gap-3">
                      <Link to={`/funds/${fund.id}`} className="group min-w-0">
                        <span className="block text-sm font-medium leading-snug group-hover:text-cobalt group-hover:underline dark:group-hover:text-cobalt-strong">
                          {fund.name}
                          <KindBadge kind={fund.kind} />
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-faint">{subline(fund)}</span>
                      </Link>
                      {full && <RankBar rank={fund.category_rank} size={fund.category_size} className="shrink-0" />}
                    </div>
                    <dl className="mt-3 grid grid-cols-3 gap-1">
                      {cards.map((c, i) => (
                        <div key={c.label}>
                          <dt className="label-caps px-2 text-right">{c.label}</dt>
                          <dd>
                            {c.heat ? (
                              <HeatCell value={c.pick(fund)} scale={cardScales[i]} />
                            ) : (
                              <span className="num block px-2 py-1.5 text-right text-sm">
                                {plainPct(c.pick(fund))}
                              </span>
                            )}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </li>
                ))}
              </ul>

              {/* Wider screens: the board. */}
              <div className="hidden overflow-x-auto border border-line bg-surface md:block">
                <table className="w-full min-w-[920px] border-collapse text-left">
                  <thead>
                    <tr className="border-b border-line">
                      <th scope="col" className="px-5 py-3">{sortButton("name", "Fund")}</th>
                      <th scope="col" className="px-3 py-3 text-right">{sortButton("latest_nav", "NAV")}</th>
                      {windows.map((w) => (
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
                      {risk && (
                        <>
                          <th scope="col" className="label-caps w-28 px-3 py-3 text-right" title="Yearly rate since the first stored NAV">
                            Since launch
                          </th>
                          <th scope="col" className="label-caps w-24 px-3 py-3 text-right" title="A year's typical swing, from daily moves">
                            Yearly swing
                          </th>
                          <th scope="col" className="label-caps w-24 px-3 py-3 text-right" title="Largest fall from a peak in the last 3 years">
                            Deepest fall
                          </th>
                        </>
                      )}
                      {full && (
                        <th scope="col" className="w-28 px-5 py-3 text-right">
                          <span className="label-caps" title="Place in its category by one-year return">
                            Rank
                          </span>
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((fund) => (
                      <tr key={fund.id} className="border-b border-line last:border-b-0 hover:bg-surface-2/50">
                        <td className="px-5 py-2">
                          <Link to={`/funds/${fund.id}`} className="group block">
                            <span className="block max-w-[26rem] truncate text-sm font-medium group-hover:text-cobalt group-hover:underline dark:group-hover:text-cobalt-strong">
                              {fund.name}
                              <KindBadge kind={fund.kind} />
                            </span>
                            <span className="block max-w-[26rem] truncate text-xs text-faint">
                              {subline(fund)}
                            </span>
                          </Link>
                        </td>
                        <td className="num px-3 py-2 text-right text-sm">
                          {fund.latest_nav != null ? fmtPrice(fund.latest_nav) : "-"}
                        </td>
                        {windows.map((w, i) => (
                          <td key={w.key} className="p-0.5">
                            <HeatCell value={w.pick(fund)} scale={scales[i]} />
                          </td>
                        ))}
                        {risk && (
                          <>
                            <td className="num px-3 py-2 text-right text-sm">
                              {plainPct(fund.return_since_launch_pct)}
                            </td>
                            <td className="num px-3 py-2 text-right text-sm">
                              {plainPct(fund.volatility_pct)}
                            </td>
                            <td className="num px-3 py-2 text-right text-sm">
                              {plainPct(fund.max_drawdown_pct)}
                            </td>
                          </>
                        )}
                        {full && (
                          <td className="px-5 py-2 text-right">
                            <RankBar rank={fund.category_rank} size={fund.category_size} />
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
        from mfapi.in. "-" means the stored history does not cover that window. Yearly swing is
        how much a year's return typically varies; deepest fall is the largest drop from a peak in
        the last three years. Past performance is not indicative of future results. Not
        investment advice.
      </p>
    </div>
  );
}
