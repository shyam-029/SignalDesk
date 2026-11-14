import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowDown, ArrowUp, ChevronsUpDown, X } from "lucide-react";

import { useScreener, useStockList } from "@/lib/hooks";
import type { ScreenResult } from "@/lib/types";
import { fmtSignedPct } from "@/lib/format";
import { scoreBand, valuationSemantics } from "@/lib/semantic";
import { cn } from "@/lib/utils";
import { SCREENER_PAGE_SIZE, pageCount, pageRangeLabel } from "@/lib/paging";
import { matchesFilter, median, useScreenerUniverse, type ScreenFilter } from "@/lib/universe";
import { DataState } from "@/components/data/DataState";
import { ScaleBar } from "@/components/data/ScoreBlock";
import { SectionHeader } from "@/components/data/SectionHeader";
import { MarketMap } from "@/components/landing/MarketMap";
import { StockLogo } from "@/components/stock/StockLogo";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";

const STATUSES = [
  { value: "", label: "Any" },
  { value: "undervalued", label: "Cheaper" },
  { value: "fairly_valued", label: "In line" },
  { value: "overvalued", label: "Pricier" },
] as const;

/** One-click starting points. Each is just a combination of the filters. */
const PRESETS: Array<{
  name: string;
  note: string;
  status: string;
  minP: number;
  minS: number;
}> = [
  { name: "Quality at a discount", note: "Profitable, sound, and cheaper than peers", status: "undervalued", minP: 70, minS: 70 },
  { name: "Highly profitable", note: "Profitability 80 or more", status: "", minP: 80, minS: 0 },
  { name: "Fortress balance sheets", note: "Solvency 90 or more", status: "", minP: 0, minS: 90 },
  { name: "Cheaper than peers", note: "P/E below the industry median", status: "undervalued", minP: 0, minS: 0 },
];

type SortKey = "symbol" | "sector" | "profitability" | "solvency";
type SortState = { key: SortKey; direction: "asc" | "desc" } | null;

// First click ascending, second descending (same convention as Markets).
function nextSort(current: SortState, key: SortKey): SortState {
  if (current?.key !== key) return { key, direction: "asc" };
  if (current.direction === "asc") return { key, direction: "desc" };
  return { key, direction: "asc" };
}

/**
 * Screener: a research filter over exactly what the backend implements
 * (valuation status, sector, industry, min profitability, min solvency) with
 * server-side sorting and paging.
 *
 * Three columns on a wide screen:
 *   - filters (and one-click presets) on the left;
 *   - the result table in the middle, ten rows per page;
 *   - on the right, the same filters applied to the whole universe: where
 *     the matches sit on the market map, and what they look like as a group.
 *
 * The table is the server's answer. The map and the group summary are
 * computed in the browser from the cached universe with the same filter
 * rules, so they update as a slider moves.
 */
export default function ScreenerPage() {
  // A stock page's sector or industry link opens the screener pre-filtered
  // (/screener?sector=...&industry=...).
  const [searchParams] = useSearchParams();
  const [status, setStatus] = React.useState<string>("");
  const [sector, setSector] = React.useState<string>(searchParams.get("sector") ?? "");
  const [industry, setIndustry] = React.useState<string>(searchParams.get("industry") ?? "");
  const [minP, setMinP] = React.useState(0);
  const [minS, setMinS] = React.useState(0);
  const [sort, setSort] = React.useState<SortState>(null);

  // The catalog's distinct sectors arrive with any stock-list response.
  const sectorsQuery = useStockList(1, 1);
  const sectors = sectorsQuery.data?.sectors ?? [];

  const anyFilter = minP > 0 || minS > 0 || status !== "" || sector !== "" || industry !== "";
  const reset = () => {
    setStatus("");
    setSector("");
    setIndustry("");
    setMinP(0);
    setMinS(0);
  };

  // Server-side paging: the API filters and sorts the whole universe, then
  // returns one page. Any filter or sort change starts again at page 1.
  const [page, setPage] = React.useState(1);
  React.useEffect(() => {
    setPage(1);
  }, [status, sector, industry, minP, minS, sort?.key, sort?.direction]);

  // Sliders fire on every step; the request follows a moment later.
  const [serverP, serverS] = useDebounced(minP, minS);

  const query = useScreener({
    status: status || null,
    sector: sector || null,
    industry: industry || null,
    minProfitability: serverP > 0 ? serverP : null,
    minSolvency: serverS > 0 ? serverS : null,
    sort: sort?.key,
    direction: sort?.direction,
    page,
    limit: SCREENER_PAGE_SIZE,
  });
  const totalPages = query.data ? pageCount(query.data.total, SCREENER_PAGE_SIZE) : 1;

  // The same filters as a predicate, for the map and the group summary.
  const filter = React.useMemo<ScreenFilter>(
    () => ({
      status,
      sector,
      industry,
      minProfitability: minP > 0 ? minP : null,
      minSolvency: minS > 0 ? minS : null,
    }),
    [status, sector, industry, minP, minS],
  );
  const match = React.useCallback((r: ScreenResult) => matchesFilter(r, filter), [filter]);

  const sortButton = (key: SortKey, label: string) => {
    const active = sort?.key === key;
    return (
      <button
        type="button"
        onClick={() => setSort((s) => nextSort(s, key))}
        aria-label={`Sort by ${label}`}
        className={cn(
          "inline-flex items-center gap-1 transition-colors hover:text-foreground",
          active && "text-foreground",
        )}
      >
        {label}
        {active ? (
          sort?.direction === "asc" ? (
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

  return (
    <div className="mx-auto max-w-[1500px] px-4 py-10 md:px-6">
      <SectionHeader
        kicker="Screener"
        title="Screen the universe"
        aside={
          <p className="num text-xs text-muted">
            {query.data ? `${query.data.total.toLocaleString("en-IN")} matches` : ""}
          </p>
        }
      />

      <Link
        to="/underrated"
        className="mb-6 block border border-line bg-surface px-5 py-3 text-sm transition-colors hover:border-rule"
      >
        <span className="font-semibold">Underrated scan</span>
        <span className="ml-2 text-muted">
          Good businesses whose price assumes little and which the market has not yet re-rated.
        </span>
        <span className="ml-2 text-cobalt">Open</span>
      </Link>

      <div className="grid gap-6 lg:grid-cols-12">
        {/* ---- Left: filters ---- */}
        <aside className="lg:col-span-3">
          <form
            className="border border-line bg-surface lg:sticky lg:top-20"
            onSubmit={(e) => e.preventDefault()}
            aria-label="Screener filters"
          >
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <p className="text-sm font-semibold">Filters</p>
              <button
                type="button"
                onClick={reset}
                disabled={!anyFilter}
                className="text-xs font-medium text-muted transition-colors hover:text-foreground disabled:opacity-40"
              >
                Clear all
              </button>
            </div>

            <div className="border-b border-line px-5 py-4">
              <p className="label-caps mb-2" id="valuation-filter-label">Valuation against peers</p>
              <div
                className="grid grid-cols-4 gap-px border border-line bg-line"
                role="group"
                aria-labelledby="valuation-filter-label"
              >
                {STATUSES.map((s) => (
                  <button
                    key={s.value}
                    type="button"
                    onClick={() => setStatus(s.value)}
                    aria-pressed={status === s.value}
                    className={cn(
                      "px-1 py-2 text-xs font-medium transition-colors",
                      status === s.value
                        ? "bg-foreground text-background"
                        : "bg-surface text-muted hover:text-foreground",
                    )}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-5 border-b border-line px-5 py-4">
              <ScoreSlider label="Profitability at least" value={minP} onChange={setMinP} />
              <ScoreSlider label="Solvency at least" value={minS} onChange={setMinS} />
            </div>

            <div className="border-b border-line px-5 py-4">
              <label className="block">
                <span className="label-caps mb-2 block">Sector</span>
                <Select
                  value={sector}
                  onChange={(e) => {
                    setSector(e.target.value);
                    setIndustry("");
                  }}
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
              </label>
              {industry && (
                <p className="mt-3 flex items-center justify-between gap-2 border border-rule px-2.5 py-1.5 text-xs">
                  <span className="min-w-0 truncate">
                    <span className="text-muted">Industry </span>
                    {industry}
                  </span>
                  <button
                    type="button"
                    onClick={() => setIndustry("")}
                    aria-label={`Clear the ${industry} industry filter`}
                    className="text-faint hover:text-foreground"
                  >
                    <X className="size-3.5" />
                  </button>
                </p>
              )}
            </div>

            <div className="px-5 py-4">
              <p className="label-caps mb-2">Start from an idea</p>
              <ul className="space-y-1.5">
                {PRESETS.map((p) => {
                  const active = status === p.status && minP === p.minP && minS === p.minS;
                  return (
                    <li key={p.name}>
                      <button
                        type="button"
                        onClick={() => {
                          setStatus(p.status);
                          setMinP(p.minP);
                          setMinS(p.minS);
                        }}
                        aria-pressed={active}
                        className={cn(
                          "w-full border px-3 py-2 text-left transition-colors",
                          active ? "border-cobalt" : "border-line hover:border-rule",
                        )}
                      >
                        <span className="block text-sm font-medium">{p.name}</span>
                        <span className="block text-xs text-muted">{p.note}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          </form>
        </aside>

        {/* ---- Middle: results ---- */}
        <div className="min-w-0 lg:col-span-5">
          <DataState
            loading={query.isLoading}
            error={query.error}
            onRetry={query.refetch}
            empty={Boolean(query.data) && query.data!.items.length === 0}
            emptyTitle="No matches"
            emptyMessage="No stocks pass these filters. Loosen a threshold or clear the filters."
            skeleton={
              <div className="border border-line bg-surface">
                {Array.from({ length: SCREENER_PAGE_SIZE }).map((_, i) => (
                  <div key={i} className="h-[57px] animate-pulse border-b border-line last:border-b-0" />
                ))}
              </div>
            }
          >
            {query.data && query.data.items.length > 0 && (
              <div
                className={cn(
                  "overflow-x-auto border border-line bg-surface transition-opacity",
                  query.isFetching && "opacity-70",
                )}
              >
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b border-line text-left">
                      <th className="label-caps px-4 py-3">{sortButton("symbol", "Company")}</th>
                      <th className="label-caps px-3 py-3">{sortButton("profitability", "Profit.")}</th>
                      <th className="label-caps px-3 py-3">{sortButton("solvency", "Solvency")}</th>
                      <th className="label-caps px-3 py-3">P/E vs peers</th>
                    </tr>
                  </thead>
                  <tbody>
                    {query.data.items.map((r) => (
                      <ResultRow
                        key={r.symbol}
                        r={r}
                        onIndustry={(ind) => {
                          if (r.sector) setSector(r.sector);
                          setIndustry(ind);
                        }}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {query.data && query.data.total > SCREENER_PAGE_SIZE && (
              <nav
                aria-label="Screener pages"
                className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted"
              >
                <span className="num" aria-live="polite">
                  {pageRangeLabel(page, SCREENER_PAGE_SIZE, query.data.total)}
                </span>
                <span className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1 || query.isFetching}
                  >
                    Previous
                  </Button>
                  <span className="num">
                    Page {page} of {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages || query.isFetching}
                  >
                    Next
                  </Button>
                </span>
              </nav>
            )}
          </DataState>

          <p className="mt-4 text-xs leading-relaxed text-faint">
            Valuation compares each stock's trailing P/E with the median of its same-industry
            peers. &ldquo;Cheaper than peers&rdquo; does not mean intrinsically cheap.
          </p>
        </div>

        {/* ---- Right: the matches as a group ---- */}
        <div className="space-y-6 lg:col-span-4">
          <GroupSummary filter={filter} />
          <MarketMap match={match} />
        </div>
      </div>
    </div>
  );
}

/** Debounce the two slider values together (250 ms after the last change). */
function useDebounced(a: number, b: number): [number, number] {
  const [value, setValue] = React.useState<[number, number]>([a, b]);
  React.useEffect(() => {
    const id = window.setTimeout(() => setValue([a, b]), 250);
    return () => window.clearTimeout(id);
  }, [a, b]);
  return value;
}

function ScoreSlider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  const id = React.useId();
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="label-caps">
          {label}
        </label>
        <span className={cn("num text-sm font-semibold", value === 0 && "text-faint")}>
          {value === 0 ? "Any" : value}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        step={5}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 w-full accent-[var(--cobalt)]"
      />
    </div>
  );
}

/**
 * GroupSummary: what the current matches look like as a group, next to the
 * whole universe: their typical scores and how their P/E verdicts split.
 * Computed in the browser from the cached universe with the same filter
 * rules the server applies.
 */
function GroupSummary({ filter }: { filter: ScreenFilter }) {
  const universe = useScreenerUniverse();
  const stats = React.useMemo(() => {
    const summarise = (rows: ScreenResult[]) => {
      const verdicts = rows.filter((r) => r.valuation_status);
      const share = (s: string) =>
        verdicts.length > 0
          ? (verdicts.filter((r) => r.valuation_status === s).length / verdicts.length) * 100
          : null;
      return {
        n: rows.length,
        profitability: median(rows.flatMap((r) => (r.profitability == null ? [] : [r.profitability]))),
        solvency: median(rows.flatMap((r) => (r.solvency == null ? [] : [r.solvency]))),
        cheaper: share("undervalued"),
        inline: share("fairly_valued"),
        pricier: share("overvalued"),
      };
    };
    return {
      all: summarise(universe.rows),
      matched: summarise(universe.rows.filter((r) => matchesFilter(r, filter))),
    };
  }, [universe.rows, filter]);

  const { all, matched } = stats;
  const shareOfUniverse = all.n > 0 ? (matched.n / all.n) * 100 : 0;

  return (
    <div className="border border-line bg-surface">
      <div className="flex items-baseline justify-between border-b border-line px-5 py-3">
        <p className="text-sm font-semibold">Your matches as a group</p>
        <p className="num text-xs text-muted">
          {universe.isComplete ? `${shareOfUniverse < 1 && matched.n > 0 ? "<1" : Math.round(shareOfUniverse)}% of the universe` : ""}
        </p>
      </div>
      {universe.isLoading && all.n === 0 ? (
        <div className="space-y-3 px-5 py-5">
          <div className="h-4 w-full animate-pulse bg-surface-2" />
          <div className="h-4 w-2/3 animate-pulse bg-surface-2" />
        </div>
      ) : (
        <div className="space-y-4 px-5 py-4">
          <CompareRow label="Profitability, typical" value={matched.profitability} baseline={all.profitability} />
          <CompareRow label="Solvency, typical" value={matched.solvency} baseline={all.solvency} />
          <div>
            <p className="mb-1.5 text-xs text-muted">P/E against peers</p>
            {matched.cheaper == null ? (
              <p className="text-xs text-faint">No P/E verdicts among the matches</p>
            ) : (
              <>
                <div className="flex h-2 w-full overflow-hidden" aria-hidden>
                  <span style={{ width: `${matched.cheaper}%`, background: "var(--up)" }} />
                  <span style={{ width: `${matched.inline}%`, background: "var(--rule)" }} />
                  <span style={{ width: `${matched.pricier}%`, background: "var(--down)" }} />
                </div>
                <p className="num mt-1.5 flex justify-between text-xs">
                  <span className="text-up">{Math.round(matched.cheaper)}% cheaper</span>
                  <span className="text-muted">{Math.round(matched.inline ?? 0)}% in line</span>
                  <span className="text-down">{Math.round(matched.pricier ?? 0)}% pricier</span>
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function CompareRow({
  label,
  value,
  baseline,
}: {
  label: string;
  value: number | null;
  baseline: number | null;
}) {
  const band = scoreBand(value);
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span>
          <span className={cn("num text-sm font-semibold", band?.text ?? "text-faint")}>
            {value == null ? "-" : Math.round(value)}
          </span>
          {baseline != null && (
            <span className="num ml-2 text-faint">universe {Math.round(baseline)}</span>
          )}
        </span>
      </div>
      <div className="relative mt-1.5">
        <ScaleBar score={value} band={band} />
        {baseline != null && (
          <span
            aria-hidden
            title="Whole universe"
            className="absolute -top-1 h-3 w-px bg-foreground"
            style={{ left: `${Math.min(100, Math.max(0, baseline))}%` }}
          />
        )}
      </div>
    </div>
  );
}

function ResultRow({ r, onIndustry }: { r: ScreenResult; onIndustry: (industry: string) => void }) {
  const sem = valuationSemantics(r.valuation_status);
  const bare = r.symbol.replace(".NS", "");
  return (
    <tr className="border-b border-line last:border-b-0 hover:bg-surface-2/50">
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-3">
          <StockLogo symbol={r.symbol} name={r.name} size="sm" />
          <div className="min-w-0">
            <Link
              to={`/stocks/${bare}`}
              className="tkr block text-sm hover:text-cobalt dark:hover:text-cobalt-strong"
            >
              {bare}
            </Link>
            <span className="block max-w-56 truncate text-xs text-muted">{r.name}</span>
            {r.industry ? (
              <button
                type="button"
                onClick={() => onIndustry(r.industry!)}
                title={`Show only ${r.industry}`}
                className="block max-w-56 truncate text-left text-xs text-faint underline decoration-transparent underline-offset-2 transition-colors hover:text-foreground hover:decoration-rule"
              >
                {r.industry}
              </button>
            ) : (
              r.sector && <span className="block text-xs text-faint">{r.sector}</span>
            )}
          </div>
        </div>
      </td>
      <td className="px-3 py-2.5">
        <ScoreCell score={r.profitability} />
      </td>
      <td className="px-3 py-2.5">
        <ScoreCell score={r.solvency} />
      </td>
      <td className="px-3 py-2.5">
        {sem ? (
          <>
            <span className={cn("block text-xs font-semibold", sem.band.text)}>{sem.short}</span>
            <span className="num block text-xs text-faint">{fmtSignedPct(r.margin_pct)}</span>
          </>
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
    <div className="w-16">
      <span className={cn("num text-sm font-semibold", band?.text ?? "text-faint")}>{score ?? "-"}</span>
      {score != null && <ScaleBar score={score} band={band} className="mt-1" />}
    </div>
  );
}
