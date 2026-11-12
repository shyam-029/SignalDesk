import * as React from "react";
import { Link } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";

import { api } from "@/lib/api";
import { scoreBand } from "@/lib/semantic";
import { cn } from "@/lib/utils";

/**
 * SectorBoard: the same universe as the market map, folded by sector, as one
 * short table. Per sector: the median profitability and solvency score of
 * its companies, and the share of its P/E verdicts that read "cheaper than
 * peers". Three numbers a row, one quiet bar each, the six largest sectors
 * by default (the rest behind a toggle).
 *
 * Reads the four screener pages the map already loaded (identical query
 * keys, so no extra requests); medians are computed over the companies that
 * carry the score. Each row opens that sector in the screener.
 */

const PAGES = [1, 2, 3, 4];
/** Sectors with fewer companies than this are too thin to summarise. */
const MIN_COMPANIES = 8;
/** Rows shown before "Show all sectors". */
const DEFAULT_ROWS = 6;

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

interface SectorRow {
  sector: string;
  size: number;
  profitability: number | null;
  solvency: number | null;
  /** Share (0-100) of the sector's P/E verdicts that are "cheaper than peers". */
  cheaperPct: number | null;
}

export function SectorBoard() {
  const [showAll, setShowAll] = React.useState(false);
  const results = useQueries({
    queries: PAGES.map((page) => {
      const params = { page, limit: 250 };
      return {
        queryKey: ["screener", params],
        queryFn: () => api.screener(params),
        staleTime: 10 * 60_000,
      };
    }),
  });
  const loading = results.some((q) => q.isLoading);
  const loadedKey = results.map((q) => q.dataUpdatedAt).join("-");

  const sectors = React.useMemo<SectorRow[]>(() => {
    const groups = new Map<string, { p: number[]; s: number[]; cheaper: number; verdicts: number; n: number }>();
    for (const r of results.flatMap((q) => q.data?.items ?? [])) {
      if (!r.sector) continue;
      const g = groups.get(r.sector) ?? { p: [], s: [], cheaper: 0, verdicts: 0, n: 0 };
      g.n += 1;
      if (r.profitability != null) g.p.push(r.profitability);
      if (r.solvency != null) g.s.push(r.solvency);
      if (r.valuation_status) {
        g.verdicts += 1;
        if (r.valuation_status === "undervalued") g.cheaper += 1;
      }
      groups.set(r.sector, g);
    }
    return [...groups.entries()]
      .filter(([, g]) => g.n >= MIN_COMPANIES)
      .map(([sector, g]) => ({
        sector,
        size: g.n,
        profitability: median(g.p),
        solvency: median(g.s),
        cheaperPct: g.verdicts > 0 ? (g.cheaper / g.verdicts) * 100 : null,
      }))
      .sort((a, b) => b.size - a.size);
  }, [loadedKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const rows = showAll ? sectors : sectors.slice(0, DEFAULT_ROWS);
  const hidden = sectors.length - DEFAULT_ROWS;

  return (
    <section className="section-alt border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-16 md:px-6 md:py-20">
        <div className="grid gap-10 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <p className="label-caps mb-1.5">The map, folded by sector</p>
            <h2 className="font-display text-2xl font-semibold leading-tight tracking-[-0.01em] md:text-[26px]">
              Where the quality is, and what it costs
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              For each of the largest sectors: how profitable and how financially sound
              its typical company is, and how many of its companies trade cheaper than
              their industry peers.
            </p>
          </div>

          <div className="lg:col-span-8">
            <div className="overflow-x-auto border border-line bg-surface">
              <table className="w-full min-w-[560px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-line">
                    <th scope="col" className="label-caps px-5 py-3">Sector</th>
                    <th scope="col" className="label-caps w-36 px-4 py-3">Profitability</th>
                    <th scope="col" className="label-caps w-36 px-4 py-3">Solvency</th>
                    <th scope="col" className="label-caps w-40 px-4 py-3">Cheaper than peers</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && sectors.length === 0
                    ? Array.from({ length: DEFAULT_ROWS }, (_, i) => (
                        <tr key={i} className="border-b border-line last:border-b-0">
                          <td colSpan={4} className="px-5 py-4">
                            <div className="h-4 w-full animate-pulse bg-surface-2" />
                          </td>
                        </tr>
                      ))
                    : rows.map((s) => (
                        <tr key={s.sector} className="border-b border-line last:border-b-0 hover:bg-surface-2/50">
                          <th scope="row" className="px-5 py-3.5 text-left font-normal">
                            <Link
                              to={`/screener?sector=${encodeURIComponent(s.sector)}`}
                              className="text-sm font-medium hover:text-cobalt hover:underline dark:hover:text-cobalt-strong"
                            >
                              {s.sector}
                            </Link>
                          </th>
                          <td className="px-4 py-3.5">
                            <Measure value={s.profitability} tone={scoreBand(s.profitability)?.text} />
                          </td>
                          <td className="px-4 py-3.5">
                            <Measure value={s.solvency} tone={scoreBand(s.solvency)?.text} />
                          </td>
                          <td className="px-4 py-3.5">
                            <Measure value={s.cheaperPct} suffix="%" />
                          </td>
                        </tr>
                      ))}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-faint">
                Scores are medians, 0 to 100. Largest sectors first.
              </p>
              {hidden > 0 && (
                <button
                  type="button"
                  onClick={() => setShowAll((v) => !v)}
                  aria-expanded={showAll}
                  className="inline-flex items-center gap-1 text-xs font-medium text-muted transition-colors hover:text-foreground"
                >
                  {showAll ? "Show fewer" : "Show all sectors"}
                  <ChevronDown className={cn("size-3.5 transition-transform", showAll && "rotate-180")} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/** A number with one quiet bar under it. The number carries any color. */
function Measure({
  value,
  tone,
  suffix = "",
}: {
  value: number | null;
  tone?: string;
  suffix?: string;
}) {
  if (value == null) return <span className="num text-sm text-faint">-</span>;
  const pct = Math.min(100, Math.max(0, value));
  return (
    <div>
      <span className={cn("num text-sm font-semibold", tone ?? "text-foreground")}>
        {Math.round(value)}
        {suffix}
      </span>
      <div className="mt-1.5 h-0.5 w-full bg-line" aria-hidden>
        <div className="h-full bg-faint" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
