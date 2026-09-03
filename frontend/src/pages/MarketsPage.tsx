import * as React from "react";
import { Link } from "react-router-dom";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { useStockList } from "@/lib/hooks";
import type { StockSummary } from "@/lib/types";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DataState } from "@/components/data/DataState";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { SectionHeader } from "@/components/data/SectionHeader";

const PAGE_SIZE = 25;

/**
 * Markets — the full research universe as a server-paginated table. The API
 * owns pagination (page/limit), so the DOM stays bounded regardless of how far
 * the catalog scales (Nifty 50 → 200 → 500). TanStack Table manages the
 * columns; all data states render through DataState.
 */
export default function MarketsPage() {
  const [page, setPage] = React.useState(1);
  const [sector, setSector] = React.useState<string>("");
  const query = useStockList(page, PAGE_SIZE, sector || undefined);

  const columns = React.useMemo(() => {
    const h = createColumnHelper<StockSummary>();
    return [
      h.accessor("symbol", {
        header: "Symbol",
        cell: (info) => (
          <Link
            to={`/stocks/${info.getValue().replace(".NS", "")}`}
            className="num text-sm font-semibold text-foreground hover:text-cobalt dark:hover:text-cobalt-strong"
          >
            {info.getValue().replace(".NS", "")}
          </Link>
        ),
      }),
      h.accessor("name", {
        header: "Company",
        cell: (info) => <span className="text-sm">{info.getValue()}</span>,
      }),
      h.accessor("sector", {
        header: "Sector",
        cell: (info) => (
          <span className="text-xs text-muted">{info.getValue() ?? "—"}</span>
        ),
      }),
      h.accessor("last_price", {
        header: "Last price",
        cell: (info) => <span className="num text-sm">{fmtPrice(info.getValue())}</span>,
      }),
      h.accessor("change_pct", {
        header: "Day change",
        cell: (info) => (
          <span
            className={cn(
              "num text-sm",
              info.getValue() > 0
                ? "text-band-positive"
                : info.getValue() < 0
                  ? "text-band-weak"
                  : "text-muted",
            )}
          >
            {fmtSignedPct(info.getValue())}
          </span>
        ),
      }),
    ];
  }, []);

  const table = useReactTable({
    data: query.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true, // the API paginates; the table renders one page
    pageCount: query.data ? Math.ceil(query.data.total / PAGE_SIZE) : 0,
  });

  const total = query.data?.total ?? 0;
  const sectors = React.useMemo(() => {
    const set = new Set<string>();
    query.data?.items.forEach((s) => s.sector && set.add(s.sector));
    return [...set].sort();
    // NOTE: options derive from the current page; the API supports exact
    // sector filtering, so a chosen option stays valid across pages.
  }, [query.data]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <SectionHeader
        index="01"
        kicker="Universe"
        title="Markets"
        aside={
          <label className="flex items-center gap-2 text-xs text-muted">
            Sector
            <Select
              value={sector}
              onChange={(e) => {
                setSector(e.target.value);
                setPage(1);
              }}
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
          <div className="border border-line">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="h-11 animate-pulse border-b border-line bg-surface-2 last:border-b-0" />
            ))}
          </div>
        }
      >
        {query.data && (
          <>
            <div className="overflow-x-auto border border-line">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-line bg-surface">
                    {table.getFlatHeaders().map((header) => (
                      <th
                        key={header.id}
                        className="label-caps px-4 py-2.5 text-left"
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      className="border-b border-line last:border-b-0 hover:bg-surface-2/60"
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="px-4 py-2.5">
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
