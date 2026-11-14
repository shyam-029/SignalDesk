import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { useFund } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { NavChart } from "@/components/fund/NavChart";
import { fmtDate, fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * FundDetailPage: one fund's stored NAV series and windowed returns. The
 * chart window (1m/3m/6m/1y/3y/ALL) slices the stored history; long windows
 * are stride-downsampled by the backend so the line stays smooth without
 * plotting every trading day. 1y/3y returns are annualised. Fund holdings
 * are NOT fabricated: portfolio disclosures are the M5 data dependency and
 * the section says so until then.
 */

const WINDOWS = [
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
  { key: "1y", label: "1Y" },
  { key: "3y", label: "3Y" },
  { key: "5y", label: "5Y" },
  { key: "10y", label: "10Y" },
  { key: "all", label: "All" },
] as const;

export default function FundDetailPage() {
  const { fundId } = useParams();
  const id = fundId != null && /^\d+$/.test(fundId) ? Number(fundId) : undefined;
  const [window, setWindow] = useState<(typeof WINDOWS)[number]["key"]>("all");
  const query = useFund(id, window);
  const fund = query.data;

  const returns: Array<[string, number | null]> = [
    ["1M", fund?.return_1m_pct ?? null],
    ["3M", fund?.return_3m_pct ?? null],
    ["6M", fund?.return_6m_pct ?? null],
    ["1Y (CAGR)", fund?.return_1y_pct ?? null],
    ["3Y (CAGR)", fund?.return_3y_pct ?? null],
  ];
  // Longer windows exist only with the funds database.
  if (fund?.return_5y_pct !== undefined) {
    returns.push(
      ["5Y (CAGR)", fund.return_5y_pct ?? null],
      ["10Y (CAGR)", fund.return_10y_pct ?? null],
      ["Since launch", fund.return_since_launch_pct ?? null],
    );
  }
  const facts: Array<[string, string, string?]> = fund
    ? [
        ["Fund house", fund.fund_house ?? "-"],
        [
          "Rank in category",
          fund.category_rank != null && fund.category_size != null
            ? `${fund.category_rank} of ${fund.category_size}`
            : "-",
          "By one-year return",
        ],
        ["Launched", fund.launch_date ? fmtDate(fund.launch_date) : "-", "First NAV on record"],
        [
          "Volatility",
          fund.volatility_pct != null ? `${fund.volatility_pct.toFixed(1)}%` : "-",
          "A year, from daily moves",
        ],
        [
          "Deepest fall",
          fund.max_drawdown_pct != null ? `${fund.max_drawdown_pct.toFixed(1)}%` : "-",
          "From a peak, last 3 years",
        ],
      ]
    : [];
  const hasFacts = fund?.fund_house !== undefined;
  const navs = fund?.items ?? [];
  const chartPositive =
    navs.length > 1 ? navs[navs.length - 1].nav >= navs[0].nav : true;

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <Link
        to="/funds"
        className="label-caps inline-flex items-center gap-1.5 text-muted transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden />
        All funds
      </Link>

      <div className="mt-4">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
        >
          {fund && (
            <>
              <p className="label-caps">{fund.category ?? "Fund"}</p>
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <h1 className="mt-1 font-display text-3xl font-semibold">{fund.name}</h1>
                <p className="num text-sm text-muted">
                  Latest NAV{" "}
                  <span className="text-lg font-semibold text-foreground">
                    {fund.latest_nav != null ? fmtPrice(fund.latest_nav) : "-"}
                  </span>
                  {fund.nav_date && <span className="ml-1 text-xs text-faint">{fund.nav_date}</span>}
                </p>
              </div>
              <p className="num mt-1 text-xs text-faint">
                AMFI {fund.amfi_code}
                {fund.isin ? ` · ${fund.isin}` : ""}
                {fund.kind === "etf" ? " · ETF" : fund.plan ? ` · ${fund.plan}` : ""}
                {fund.option ? ` · ${fund.option}` : ""}
              </p>

              {hasFacts && (
                <dl className="mt-5 grid gap-px border border-line bg-line sm:grid-cols-3 lg:grid-cols-5">
                  {facts.map(([label, value, note]) => (
                    <div key={label} className="bg-surface p-4">
                      <dt className="label-caps">{label}</dt>
                      <dd className="num mt-1 text-sm font-medium">{value}</dd>
                      {note && <dd className="mt-0.5 text-[11px] text-faint">{note}</dd>}
                    </div>
                  ))}
                </dl>
              )}

              {/* NAV chart with window selector */}
              <div className="mt-6 border border-line bg-surface">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-2.5">
                  <p className="label-caps">NAV history</p>
                  <div className="flex flex-wrap gap-1">
                    {WINDOWS.map((w) => (
                      <button
                        key={w.key}
                        type="button"
                        onClick={() => setWindow(w.key)}
                        aria-pressed={window === w.key}
                        className={cn(
                          "border px-2 py-0.5 text-xs font-medium transition-colors",
                          window === w.key
                            ? "border-cobalt bg-surface-2 text-foreground"
                            : "border-line text-muted hover:text-foreground",
                        )}
                      >
                        {w.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="px-5 py-4">
                  <NavChart points={navs} positive={chartPositive} />
                  <p className="num mt-2 text-xs text-faint">
                    {fund.nav_points} stored NAV point{fund.nav_points === 1 ? "" : "s"}
                    {fund.history_start && fund.history_end
                      ? ` · inception in chart: ${fund.history_start} to ${fund.history_end}`
                      : ""}
                    {" · long windows are sampled for smoothness"}
                  </p>
                </div>
              </div>

              {/* Returns */}
              <div
                className={cn(
                  "mt-6 grid gap-px border border-line bg-line sm:grid-cols-3",
                  returns.length > 5 ? "lg:grid-cols-4" : "lg:grid-cols-5",
                )}
              >
                {returns.map(([label, value]) => (
                  <div key={label} className="bg-surface p-5">
                    <p className="label-caps">{label}</p>
                    <p
                      className={cn(
                        "num mt-1 text-2xl font-medium",
                        value == null
                          ? "text-faint"
                          : value >= 0
                            ? "text-up"
                            : "text-down",
                      )}
                    >
                      {fmtSignedPct(value)}
                    </p>
                  </div>
                ))}
              </div>

              {/* Holdings: honest absence until portfolio disclosures land (M5). */}
              <div className="mt-6 border border-line bg-surface">
                <div className="border-b border-line px-5 py-3">
                  <p className="label-caps">Portfolio holdings</p>
                </div>
                <div className="px-5 py-6">
                  <p className="text-sm font-semibold">Not ingested yet</p>
                  <p className="mt-1 max-w-xl text-xs leading-relaxed text-muted">
                    Fund-house monthly portfolio disclosures are the next data
                    dependency (Excel-first ingestion). When they arrive, this
                    section will list the stocks the fund holds with their
                    weights, each linking to its research page. Nothing is
                    estimated in the meantime.
                  </p>
                </div>
              </div>

              <p className="mt-4 text-xs leading-relaxed text-faint">
                NAVs are daily close values from AMFI (official) with a
                documented fallback backfill marked per row. Returns are
                computed from stored history only; 1Y and longer are annualised. Past
                performance is not indicative of future results. Not
                investment advice.
              </p>
            </>
          )}
        </DataState>
      </div>
    </div>
  );
}
