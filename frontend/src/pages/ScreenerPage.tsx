import * as React from "react";
import { Link } from "react-router-dom";
import { RotateCcw, Search } from "lucide-react";

import { useScreener } from "@/lib/hooks";
import type { ScreenResult } from "@/lib/types";
import { fmtSignedPct } from "@/lib/format";
import { scoreBand, valuationSemantics } from "@/lib/semantic";
import { cn } from "@/lib/utils";
import { DataState } from "@/components/data/DataState";
import { SectionHeader } from "@/components/data/SectionHeader";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";

const STATUSES = [
  { value: "", label: "All valuation states" },
  { value: "undervalued", label: "Undervalued" },
  { value: "fairly_valued", label: "Fairly valued" },
  { value: "overvalued", label: "Overvalued" },
] as const;

/**
 * Screener — a research filter over the exact capabilities the backend
 * implements (valuation status, min profitability, min solvency). No invented
 * filters; thresholds are clamped client-side and validated by the API.
 */
export default function ScreenerPage() {
  const [status, setStatus] = React.useState<string>("");
  const [minProfitability, setMinProfitability] = React.useState<string>("");
  const [minSolvency, setMinSolvency] = React.useState<string>("");

  const clamp100 = (raw: string): number | null => {
    if (raw.trim() === "") return null;
    const n = Number(raw);
    if (Number.isNaN(n)) return null;
    return Math.min(100, Math.max(0, n));
  };

  const minP = clamp100(minProfitability);
  const minS = clamp100(minSolvency);

  const anyFilter = minP != null || minS != null || status !== "";

  const query = useScreener({
    status: status || null,
    minProfitability: minP,
    minSolvency: minS,
    page: 1,
    limit: 200,
  });

  const columns: Array<{ key: keyof ScreenResult; header: string; render: (r: ScreenResult) => React.ReactNode }> = [
    {
      key: "symbol",
      header: "Symbol",
      render: (r) => (
        <Link
          to={`/stocks/${r.symbol.replace(".NS", "")}`}
          className="num text-sm font-semibold text-foreground hover:text-cobalt dark:hover:text-cobalt-strong"
        >
          {r.symbol.replace(".NS", "")}
        </Link>
      ),
    },
    {
      key: "name",
      header: "Company",
      render: (r) => <span className="text-sm">{r.name}</span>,
    },
    {
      key: "industry",
      header: "Sector / Industry",
      render: (r) => (
        <span className="text-xs text-muted">
          {r.sector ?? "—"}
          {r.industry ? <span className="text-faint"> · {r.industry}</span> : null}
        </span>
      ),
    },
    {
      key: "profitability",
      header: "Profitability",
      render: (r) => <ScoreCell score={r.profitability} />,
    },
    {
      key: "solvency",
      header: "Solvency",
      render: (r) => <ScoreCell score={r.solvency} />,
    },
    {
      key: "valuation_status",
      header: "Valuation (P/E)",
      render: (r) => {
        const sem = valuationSemantics(r.valuation_status);
        return (
          <span className="flex flex-col items-start gap-0.5">
            {sem && (
              <span className={`border px-1.5 py-0.5 text-[11px] font-medium ${sem.band.text} ${sem.band.border} ${sem.band.bg.replace("/10", "/6")}`}>
                {sem.short}
              </span>
            )}
            <span className="num text-[11px] text-faint">{fmtSignedPct(r.margin_pct)}</span>
          </span>
        );
      },
    },
  ];

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <SectionHeader
        index="02"
        kicker="Screener"
        title="Screen the universe"
        aside={
          <p className="num text-xs text-muted">
            {query.data ? `${query.data.total} matches` : "—"}
          </p>
        }
      />

      {/* Filter bar — backed 1:1 by GET /screener query params. */}
      <form
        className="mb-6 flex flex-wrap items-center gap-3 border border-line bg-surface px-4 py-3"
        onSubmit={(e) => e.preventDefault()}
        aria-label="Screener filters"
      >
        <Search className="size-4 text-faint" />
        <label className="flex items-center gap-2 text-xs text-muted">
          Valuation
          <Select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="w-44"
            aria-label="Valuation status"
          >
            {STATUSES_TO_OPTIONS}
          </Select>
        </label>
        <label className="flex items-center gap-2 text-xs text-muted">
          Min profitability
          <Input
            type="number"
            min={0}
            max={100}
            value={minProfitability}
            onChange={(e) => setMinProfitability(e.target.value)}
            placeholder="0–100"
            aria-label="Minimum profitability score"
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-muted">
          Min solvency
          <Input
            type="number"
            min={0}
            max={100}
            value={minSolvency}
            onChange={(e) => setMinSolvency(e.target.value)}
            placeholder="0–100"
            aria-label="Minimum solvency score"
          />
        </label>
        {anyFilter && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="gap-1 text-xs"
            onClick={() => {
              setStatus("");
              setMinProfitability("");
              setMinSolvency("");
            }}
          >
            <RotateCcw className="size-3.5" /> Reset
          </Button>
        )}
      </form>

      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={Boolean(query.data) && query.data!.items.length === 0}
        emptyTitle="No matches"
        emptyMessage="No stocks pass these filters. Loosen a threshold or clear the filters."
        skeleton={
          <div className="border border-line">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-11 animate-pulse border-b border-line bg-surface-2 last:border-b-0" />
            ))}
          </div>
        }
      >
        {query.data && query.data.items.length > 0 && (
          <div className="overflow-x-auto border border-line">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-line bg-surface">
                  {columns.map((c) => (
                    <th key={c.key} className="label-caps px-4 py-2.5 text-left">
                      {c.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((r) => (
                  <tr key={r.symbol} className="border-b border-line last:border-b-0 hover:bg-surface-2/60">
                    {columns.map((c) => (
                      <td key={c.key} className="px-4 py-2.5">
                        {c.render(r)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataState>

      <p className="mt-4 text-[11px] leading-relaxed text-faint">
        Valuation status compares each stock's trailing P/E with the median of its
        same-industry peers. &ldquo;Cheaper than peers&rdquo; does not mean intrinsically cheap.
      </p>
    </div>
  );
}

function ScoreCell({ score }: { score: number | null }) {
  const band = scoreBand(score);
  return (
    <span className="flex items-center gap-2">
      <span className={cn("num text-sm font-medium", band?.text)}>
        {score ?? "—"}
      </span>
      <span className="hidden h-1 w-14 bg-line sm:block">
        <span
          className={cn("block h-full", band?.bar ?? "bg-faint")}
          style={{ width: `${score ?? 0}%` }}
        />
      </span>
    </span>
  );
}

const STATUSES_TO_OPTIONS = STATUSES.map((s) => (
  <option key={s.value} value={s.value}>
    {s.label}
  </option>
));
