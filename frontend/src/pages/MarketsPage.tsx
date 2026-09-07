import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";

import { useStockList } from "@/lib/hooks";
import type { StockSummary } from "@/lib/types";
import { fmtMarketCap, fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DataState } from "@/components/data/DataState";
import { StockLogo } from "@/components/stock/StockLogo";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { SectionHeader } from "@/components/data/SectionHeader";

const PAGE_SIZE = 25;

type SortKey = "symbol" | "company" | "sector" | "last_price" | "change_pct" | "market_cap";
type SortState = { key: SortKey; direction: "asc" | "desc" } | null;

// Click behavior per the product decision: first click sorts ascending,
// second click descending, third click back to ascending.
function nextSort(current: SortState, key: SortKey): SortState {
  if (current?.key !== key) return { key, direction: "asc" };
  if (current.direction === "asc") return { key, direction: "desc" };
  return { key, direction: "asc" };
}

/**
 * Markets: the full research universe (Nifty 250) as a server-paginated,
 * server-sorted table. The API owns pagination AND ordering, so the DOM stays
 * bounded regardless of catalog scale. Sector cells link to the
 * sector-filtered list; the sector filter stays in the header.
 */
export default function MarketsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const sectorParam = searchParams.get("sector") ?? "";
  const [page, setPage] = React.useState(1);
  const [sort, setSort] = React.useState<SortState>(null);
  const query = useStockList(
    page,
    PAGE_SIZE,
    sectorParam || undefined,
    sort?.key,
    sort?.direction,
  );

  const setSector = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set("sector", value);
    else next.delete("sector");
    setSearchParams(next, { replace: true });
    setPage(1);
  };

  const columns = React.useMemo(() => {
    const h = createColumnHelper<StockSummary>();
    return [
      h.accessor("symbol", {
        header: "Symbol",
        cell: (info) => (
          <Link
            to={`/stocks/${info.getValue().replace(".NS", "")}`}
            className="group flex items-center gap-3"
          >
            <StockLogo symbol={info.getValue()} name={info.row.original.name} size="sm" />
            <span className="min-w-0">
              <span className="num block text-sm font-semibold text-foreground group-hover:text-cobalt dark:group-hover:text-cobalt-strong">
                {info.getValue().replace(".NS", "")}
              </span>
              <span className="block max-w-52 truncate text-xs text-muted">
                {info.row.original.name}
              </span>
            </span>
          </Link>
        ),
      }),
      h.accessor("sector", {
        header: "Sector",
        cell: (info) => {
          const sector = info.getValue();
          return sector ? (
            <Link
              to={`/markets?sector=${encodeURIComponent(sector)}`}
              className="text-xs font-medium text-muted underline decoration-line underline-offset-4 hover:text-cobalt hover:decoration-cobalt dark:hover:text-cobalt-strong"
            >
              {sector}
            </Link>
          ) : (
            <span className="text-xs text-faint">-</span>
          );
        },
      }),
      h.accessor("market_cap", {
        header: "Market cap",
        cell: (info) => (
          <span className="num text-sm font-medium">{fmtMarketCap(info.getValue())}</span>
        ),
      }),
      h.accessor("last_price", {
        header: "Last price",
        cell: (info) => <span className="num text-sm font-semibold">{fmtPrice(info.getValue())}</span>,
      }),
      h.accessor("change_pct", {
        header: "Day change",
        cell: (info) => {
          const v = info.getValue();
          if (v == null) {
            return <span className="num text-sm text-faint">-</span>;
          }
          const up = v > 0;
          const down = v < 0;
          return (
            <span
              className={cn(
                "num inline-flex items-center gap-1 text-sm font-semibold",
                up ? "text-band-positive" : down ? "text-band-weak" : "text-muted",
              )}
            >
              {up && <ArrowUp className="size-3.5" aria-label="up" />}
              {down && <ArrowDown className="size-3.5" aria-label="down" />}
              {fmtSignedPct(v)}
            </span>
          );
        },
      }),
    ];
  }, []);

  const table = useReactTable({
    data: query.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true, // the API paginates + sorts; the table renders one page
    pageCount: query.data ? Math.ceil(query.data.total / PAGE_SIZE) : 0,
  });

  const total = query.data?.total ?? 0;
  const sectors = query.data?.sectors ?? [];

  const sortButton = (key: SortKey, label: string, align: "left" | "right" = "left") => {
    const active = sort?.key === key;
    return (
      <button
        onClick={() => {
          setSort((s) => nextSort(s, key));
          setPage(1);
        }}
        aria-label={`Sort by ${label}`}
        className={cn(
          "group inline-flex items-center gap-1 transition-colors hover:text-cobalt dark:hover:text-cobalt-strong",
          active && "text-cobalt dark:text-cobalt-strong",
          align === "right" && "flex-row-reverse",
        )}
      >
        {label}
        {active ? (
          sort?.direction === "asc" ? (
            <ChevronUp className="size-3.5" />
          ) : (
            <ChevronDown className="size-3.5" />
          )
        ) : (
          <ChevronDown className="size-3.5 opacity-0 transition-opacity group-hover:opacity-60" />
        )}
      </button>
    );
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <SectionHeader
        index="01"
        kicker="Universe · Nifty 250"
        title="Markets"
        aside={
          <label className="flex items-center gap-2 text-xs text-muted">
            Sector
            <Select
              value={sectorParam}
              onChange={(e) => setSector(e.target.value)}
              className="w-44"
              aria-label="Filter by sector"
            >
              <option value="">All sectors</option>
              {sectors.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </label>
        }
      />

      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={Boolean(query.data) && total === 0}
        emptyTitle="No stocks match"
        emptyMessage="Try a different sector filter."
        skeleton={
          <div className="glass rounded-sm">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="h-11 animate-pulse border-b border-line last:border-b-0" />
            ))}
          </div>
        }
      >
        {query.data && (
          <>
            <div className="glass overflow-x-auto rounded-sm">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-line bg-surface/70">
                    <th className="label-caps px-4 py-3 text-left">
                      {sortButton("symbol", "Company")}
                    </th>
                    <th className="label-caps px-4 py-3 text-left">
                      {sortButton("sector", "Sector")}
                    </th>
                    <th className="label-caps px-4 py-3 text-right">
                      {sortButton("market_cap", "Market cap", "right")}
                    </th>
                    <th className="label-caps px-4 py-3 text-right">
                      {sortButton("last_price", "Last price", "right")}
                    </th>
                    <th className="label-caps px-4 py-3 text-right">
                      {sortButton("change_pct", "Day change", "right")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      className="border-b border-line last:border-b-0 hover:bg-surface-2/60"
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="px-4 py-3">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <p className="num text-xs text-muted">
                {total} companies · page {page} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1 || query.isFetching}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  <ChevronLeft className="size-4" /> Prev
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= Math.ceil(total / PAGE_SIZE) || query.isFetching}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </DataState>
    </div>
  );
}
