import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, X } from "lucide-react";

import { api, type ScreenerParams } from "@/lib/api";
import { useStockList } from "@/lib/hooks";
import type { ScreenResult } from "@/lib/types";
import { fmtSignedPct } from "@/lib/format";
import { scoreBand, valuationSemantics } from "@/lib/semantic";
import { cn } from "@/lib/utils";
import { DataState } from "@/components/data/DataState";
import { ScaleBar } from "@/components/data/ScoreBlock";
import { SectionHeader } from "@/components/data/SectionHeader";
import { StockLogo } from "@/components/stock/StockLogo";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";

const STATUSES = [
  { value: "", label: "Any valuation" },
  { value: "undervalued", label: "Undervalued" },
  { value: "fairly_valued", label: "Fairly valued" },
  { value: "overvalued", label: "Overvalued" },
] as const;

type SortKey = "symbol" | "sector" | "profitability" | "solvency";
const SORT_KEYS: readonly SortKey[] = ["symbol", "sector", "profitability", "solvency"];

/** Rows shown per page. */
const PAGE_SIZE = 10;
/** Rows fetched per request: three pages at a time, so paging is instant. */
const CHUNK = PAGE_SIZE * 3;
/** The API's hard page-size ceiling; used only for the industry view. */
const MAX_LIMIT = 250;

function clamp100(raw: string | null): number | null {
  if (raw == null || raw.trim() === "") return null;
  const n = Number(raw);
  if (Number.isNaN(n)) return null;
  return Math.min(100, Math.max(0, n));
}

/**
 * Screener: a research filter over exactly what the backend implements
 * (valuation status, sector, min profitability, min solvency) with
 * server-side sorting and paging.
 *
 * - Every filter, the sort and the page live in the URL, so a screen can be
 *   bookmarked, shared, and reached from a stock's sector/industry link.
 * - Ten rows per page. Rows arrive three pages at a time and the next chunk
 *   is prefetched, so the table never waits on the full universe.
 * - Industry has no server-side filter: when an industry is requested the
 *   page loads that industry's sector once and narrows it in the browser.
 */
export default function ScreenerPage() {
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();

  const status = params.get("status") ?? "";
  const sector = params.get("sector") ?? "";
  // An industry is only meaningful inside its sector (the server filters by
  // sector; the browser narrows to the industry).
  const industry = sector ? (params.get("industry") ?? "") : "";
  const minProfitability = params.get("min_profitability") ?? "";
  const minSolvency = params.get("min_solvency") ?? "";
  const sortParam = params.get("sort") as SortKey | null;
  const sort = sortParam && SORT_KEYS.includes(sortParam) ? sortParam : null;
  const direction = params.get("direction") === "desc" ? "desc" : "asc";
  const page = Math.max(1, Number(params.get("page")) || 1);

  /** Update URL params; any filter change returns to page 1. */
  const update = (changes: Record<string, string | null>, keepPage = false) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(changes)) {
          if (v == null || v === "") next.delete(k);
          else next.set(k, v);
        }
        if (!keepPage) next.delete("page");
        return next;
      },
      { replace: true },
    );
  };

  // The catalog's distinct sectors arrive with any stock-list response.
  const sectorsQuery = useStockList(1, 1);
  const sectors = sectorsQuery.data?.sectors ?? [];

  const filters: ScreenerParams = {
    status: status || null,
    sector: sector || null,
    minProfitability: clamp100(minProfitability),
    minSolvency: clamp100(minSolvency),
    sort: sort ?? undefined,
    direction: sort ? direction : undefined,
  };

  // Industry view: one request for the whole sector, narrowed client-side.
  // Otherwise: the chunk (three pages) that contains the current page.
  const chunkIndex = Math.floor((page - 1) / 3) + 1;
  const request: ScreenerParams = industry
    ? { ...filters, page: 1, limit: MAX_LIMIT }
    : { ...filters, page: chunkIndex, limit: CHUNK };

  const query = useQuery({
    queryKey: ["screener", request],
    queryFn: () => api.screener(request),
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });

  const fetched = query.data?.items ?? [];
  const matching = industry ? fetched.filter((r) => r.industry === industry) : fetched;
  const total = industry ? matching.length : (query.data?.total ?? 0);
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const offset = industry ? (page - 1) * PAGE_SIZE : ((page - 1) % 3) * PAGE_SIZE;
  const rows = matching.slice(offset, offset + PAGE_SIZE);

  // Warm the next chunk so "next" past the third page is also instant.
  React.useEffect(() => {
    if (industry || !query.data) return;
    if (chunkIndex * CHUNK >= query.data.total) return;
    const next: ScreenerParams = { ...filters, page: chunkIndex + 1, limit: CHUNK };
    void queryClient.prefetchQuery({
      queryKey: ["screener", next],
      queryFn: () => api.screener(next),
      staleTime: 5 * 60_000,
    });
    // `filters` is derived from the URL params captured in the query key.
  }, [query.data, chunkIndex, industry]); // eslint-disable-line react-hooks/exhaustive-deps

  const anyFilter =
    status !== "" || sector !== "" || minProfitability !== "" || minSolvency !== "";

  const toggleSort = (key: SortKey) => {
    if (sort !== key) update({ sort: key, direction: "asc" });
    else update({ sort: key, direction: direction === "asc" ? "desc" : "asc" });
  };

  const sortHeader = (key: SortKey, label: string) => {
    const active = sort === key;
    return (
      <button
        type="button"
        onClick={() => toggleSort(key)}
        aria-label={`Sort by ${label}`}
        className={cn(
          "inline-flex items-center gap-1 uppercase tracking-[0.14em] transition-colors hover:text-foreground",
          active && "text-foreground",
        )}
      >
        {label}
        {active ? (
          direction === "asc" ? (
            <ArrowUp className="size-3" />
          ) : (
            <ArrowDown className="size-3" />
          )
        ) : (
          <ChevronsUpDown className="size-3 opacity-40" />
        )}
      </button>
    );
  };

  const first = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const last = Math.min(page * PAGE_SIZE, total);

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 md:px-6">
      <SectionHeader
        kicker="Screener"
        title="Screen the universe"
        aside={
          <p className="num text-xs text-muted">
            {query.data ? `${total.toLocaleString("en-IN")} matches` : ""}
          </p>
        }
      />

      {/* Filter bar, backed 1:1 by GET /screener query params. */}
      <form
        className="mb-4 grid gap-3 border border-line bg-surface p-4 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_auto_auto_auto]"
        onSubmit={(e) => e.preventDefault()}
        aria-label="Screener filters"
      >
        <Field label="Valuation">
          <Select
            value={status}
            onChange={(e) => update({ status: e.target.value })}
            className="w-full"
            aria-label="Valuation status"
          >
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Sector">
          <Select
            value={sector}
            onChange={(e) => update({ sector: e.target.value, industry: null })}
            className="w-full"
            aria-label="Filter by sector"
          >
            <option value="">All sectors</option>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Min profitability">
          <Input
            type="number"
            min={0}
            max={100}
            value={minProfitability}
            onChange={(e) => update({ min_profitability: e.target.value })}
            placeholder="0-100"
            aria-label="Minimum profitability score"
          />
        </Field>
        <Field label="Min solvency">
          <Input
            type="number"
            min={0}
            max={100}
            value={minSolvency}
            onChange={(e) => update({ min_solvency: e.target.value })}
            placeholder="0-100"
            aria-label="Minimum solvency score"
          />
        </Field>
        <div className="flex items-end">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-9 text-xs"
            disabled={!anyFilter}
            onClick={() =>
              update({
                status: null,
                sector: null,
                industry: null,
                min_profitability: null,
                min_solvency: null,
              })
            }
          >
            Clear filters
          </Button>
        </div>
      </form>

      {industry && (
        <p className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted">
          Industry
          <span className="inline-flex items-center gap-1.5 border border-rule bg-surface px-2 py-1 font-medium text-foreground">
            {industry}
            <button
              type="button"
              aria-label="Remove industry filter"
              onClick={() => update({ industry: null })}
              className="text-faint transition-colors hover:text-foreground"
            >
              <X className="size-3" />
            </button>
          </span>
        </p>
      )}

      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={Boolean(query.data) && total === 0}
        emptyTitle="No matches"
        emptyMessage="No stocks pass these filters. Loosen a threshold or clear the filters."
        skeleton={<TableSkeleton />}
      >
        {rows.length > 0 && (
          <div
            className={cn(
              "overflow-x-auto border border-line bg-surface transition-opacity",
              query.isPlaceholderData && "opacity-60",
            )}
          >
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-line text-left text-xs font-semibold text-faint">
                  <th className="px-4 py-3">{sortHeader("symbol", "Company")}</th>
                  <th className="px-4 py-3">{sortHeader("sector", "Sector")}</th>
                  <th className="px-4 py-3">{sortHeader("profitability", "Profitability")}</th>
                  <th className="px-4 py-3">{sortHeader("solvency", "Solvency")}</th>
                  <th className="px-4 py-3 uppercase tracking-[0.14em]">Valuation (P/E)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <Row
                    key={r.symbol}
                    r={r}
                    onIndustry={(ind) => update({ sector: r.sector, industry: ind })}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {total > 0 && (
          <nav
            aria-label="Screener pages"
            className="mt-3 flex items-center justify-between gap-3 text-xs text-muted"
          >
            <p className="num">
              {first}-{last} of {total.toLocaleString("en-IN")}
            </p>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 gap-1 px-2 text-xs"
                disabled={page <= 1}
                onClick={() => update({ page: String(page - 1) }, true)}
              >
                <ChevronLeft className="size-3.5" /> Prev
              </Button>
              <span className="num px-2">
                Page {page} of {pageCount}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 gap-1 px-2 text-xs"
                disabled={page >= pageCount}
                onClick={() => update({ page: String(page + 1) }, true)}
              >
                Next <ChevronRight className="size-3.5" />
              </Button>
            </div>
          </nav>
        )}
      </DataState>

      <p className="mt-6 max-w-3xl text-xs leading-relaxed text-faint">
        Valuation status compares each stock's trailing P/E with the median of its
        same-industry peers. &ldquo;Cheaper than peers&rdquo; does not mean intrinsically cheap.
      </p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label-caps mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}

function Row({ r, onIndustry }: { r: ScreenResult; onIndustry: (industry: string) => void }) {
  const sem = valuationSemantics(r.valuation_status);
  const bare = r.symbol.replace(".NS", "");
  return (
    <tr className="border-b border-line last:border-b-0 hover:bg-surface-2/50">
      <td className="px-4 py-2.5">
        <Link to={`/stocks/${bare}`} className="group flex items-center gap-3">
          <StockLogo symbol={r.symbol} name={r.name} size="sm" />
          <span className="min-w-0">
            <span className="num block text-sm font-semibold text-foreground group-hover:text-cobalt dark:group-hover:text-cobalt-strong">
              {bare}
            </span>
            <span className="block max-w-56 truncate text-xs text-muted">{r.name}</span>
          </span>
        </Link>
      </td>
      <td className="px-4 py-2.5 text-xs">
        <span className="block font-medium text-muted">{r.sector ?? "-"}</span>
        {r.industry && r.sector && (
          <button
            type="button"
            onClick={() => onIndustry(r.industry!)}
            title={`Show only ${r.industry}`}
            className="text-left text-faint underline decoration-transparent underline-offset-2 transition-colors hover:text-foreground hover:decoration-rule"
          >
            {r.industry}
          </button>
        )}
      </td>
      <td className="px-4 py-2.5">
        <ScoreCell score={r.profitability} />
      </td>
      <td className="px-4 py-2.5">
        <ScoreCell score={r.solvency} />
      </td>
      <td className="px-4 py-2.5">
        {sem ? (
          <span className="flex items-baseline gap-2">
            <span className={cn("text-xs font-semibold", sem.band.text)}>{sem.short}</span>
            <span className="num text-xs text-faint">{fmtSignedPct(r.margin_pct)}</span>
          </span>
        ) : (
          <span className="text-xs text-faint" title="The snapshot lacks the P/E inputs for this stock">
            -
          </span>
        )}
      </td>
    </tr>
  );
}

function ScoreCell({ score }: { score: number | null }) {
  const band = scoreBand(score);
  return (
    <span className="flex items-center gap-2.5">
      <span className={cn("num w-7 text-sm font-semibold", band?.text ?? "text-faint")}>
        {score ?? "-"}
      </span>
      {score != null && <ScaleBar score={score} band={band} className="hidden w-16 sm:block" />}
    </span>
  );
}

function TableSkeleton() {
  return (
    <div className="border border-line bg-surface">
      {Array.from({ length: PAGE_SIZE }).map((_, i) => (
        <div key={i} className="flex h-[53px] items-center gap-3 border-b border-line px-4 last:border-b-0">
          <div className="size-6 animate-pulse bg-surface-2" />
          <div className="h-3 w-40 animate-pulse bg-surface-2" />
        </div>
      ))}
    </div>
  );
}
