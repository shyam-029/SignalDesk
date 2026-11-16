import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { useFund } from "@/lib/hooks";
import type { FundDetailResponse } from "@/lib/types";
import { DataState } from "@/components/data/DataState";
import { StatTiles, type StatTile } from "@/components/data/StatTiles";
import { NavChart } from "@/components/fund/NavChart";
import { RankBar } from "@/components/fund/RankBar";
import {
  fmtRupees,
  grewTo,
  kindLabel,
  rankPosition,
  spanInWords,
} from "@/components/fund/fundFormat";
import { fmtDate, fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * FundDetailPage: one fund read top to bottom. Headline figures, the NAV
 * chart (the window slices stored history; long windows are sampled by the
 * backend), every return beside what 10,000 rupees became over that window,
 * and the ride in plain words. Every rupee figure is arithmetic on the stored
 * returns and NAVs, never a projection. Fund holdings are NOT fabricated: the
 * section says they are not collected yet.
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

const START = 10_000;

interface ReturnRow {
  label: string;
  value: number | null;
  /** Years the yearly rate applies to; 0 for a plain return under a year. */
  years: number;
}

function yearsBetween(fromIso: string | null | undefined, toIso: string | null | undefined): number {
  if (!fromIso || !toIso) return 0;
  return (new Date(toIso).getTime() - new Date(fromIso).getTime()) / (365.25 * 86_400_000);
}

function returnRows(fund: FundDetailResponse): { short: ReturnRow[]; long: ReturnRow[] } {
  const short: ReturnRow[] = [
    { label: "1 month", value: fund.return_1m_pct, years: 0 },
    { label: "3 months", value: fund.return_3m_pct, years: 0 },
    { label: "6 months", value: fund.return_6m_pct, years: 0 },
  ];
  const long: ReturnRow[] = [
    { label: "1 year", value: fund.return_1y_pct, years: 1 },
    { label: "3 years", value: fund.return_3y_pct, years: 3 },
  ];
  // Longer windows exist only with the funds database.
  if (fund.return_5y_pct !== undefined) {
    long.push(
      { label: "5 years", value: fund.return_5y_pct ?? null, years: 5 },
      { label: "10 years", value: fund.return_10y_pct ?? null, years: 10 },
      {
        label: "Since launch",
        value: fund.return_since_launch_pct ?? null,
        years: yearsBetween(fund.launch_date ?? fund.history_start, fund.nav_date),
      },
    );
  }
  return { short, long };
}

function tone(v: number | null | undefined): "up" | "down" | undefined {
  return v == null ? undefined : v >= 0 ? "up" : "down";
}

function ReturnTable({ title, note, rows }: { title: string; note: string; rows: ReturnRow[] }) {
  return (
    <tbody>
      <tr className="border-b border-line bg-surface-2">
        <th scope="colgroup" colSpan={3} className="px-5 py-2 text-left">
          <span className="label-caps">{title}</span>
          <span className="ml-2 text-[11px] font-normal text-faint">{note}</span>
        </th>
      </tr>
      {rows.map((r) => {
        // A since-launch rate under a year old is not a yearly rate worth compounding.
        const became = r.label === "Since launch" && r.years < 1 ? null : grewTo(r.value, r.years, START);
        return (
          <tr key={r.label} className="border-b border-line last:border-b-0">
            <th scope="row" className="px-5 py-2.5 text-left text-sm font-normal text-muted">
              {r.label}
            </th>
            <td
              className={cn(
                "num px-3 py-2.5 text-right text-sm font-medium",
                r.value == null ? "text-faint" : r.value >= 0 ? "text-up" : "text-down",
              )}
            >
              {fmtSignedPct(r.value)}
            </td>
            <td className="num px-5 py-2.5 text-right text-sm">{fmtRupees(became)}</td>
          </tr>
        );
      })}
    </tbody>
  );
}

function Card({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn("border border-line bg-surface", className)}>
      <div className="border-b border-line px-5 py-3">
        <h2 className="label-caps">{title}</h2>
      </div>
      {children}
    </section>
  );
}

export default function FundDetailPage() {
  const { fundId } = useParams();
  const id = fundId != null && /^\d+$/.test(fundId) ? Number(fundId) : undefined;
  const [window, setWindow] = useState<(typeof WINDOWS)[number]["key"]>("all");
  const query = useFund(id, window);
  const fund = query.data;

  const fromDb = fund?.fund_house !== undefined;
  const navs = fund?.items ?? [];
  const first = navs[0];
  const last = navs[navs.length - 1];
  const chartPositive = navs.length > 1 ? last.nav >= first.nav : true;
  const windowGrew = navs.length > 1 && first.nav > 0 ? (START * last.nav) / first.nav : null;
  const rows = fund ? returnRows(fund) : null;
  const pos = fund ? rankPosition(fund.category_rank, fund.category_size) : null;
  const fall = fund?.max_drawdown_pct ?? null;
  const swing = fund?.volatility_pct ?? null;

  const tags = fund
    ? [
        fund.asset_group ? fund.asset_group[0].toUpperCase() + fund.asset_group.slice(1) : null,
        fund.category,
        kindLabel(fund.kind),
        fund.kind === "etf" ? null : fund.plan,
        fund.option,
      ].filter((t): t is string => Boolean(t))
    : [];

  const tiles: StatTile[] = fund
    ? [
        { label: "1 year", value: fmtSignedPct(fund.return_1y_pct), tone: tone(fund.return_1y_pct) },
        {
          label: "3 years",
          value: fmtSignedPct(fund.return_3y_pct),
          tone: tone(fund.return_3y_pct),
          note: "A year",
        },
        ...(fromDb
          ? [
              {
                label: "5 years",
                value: fmtSignedPct(fund.return_5y_pct),
                tone: tone(fund.return_5y_pct),
                note: "A year",
              } satisfies StatTile,
              {
                label: "Rank in category",
                value: <RankBar rank={fund.category_rank} size={fund.category_size} align="left" />,
                note:
                  fund.category_rank != null && fund.category_size != null
                    ? `${fund.category_rank} of ${fund.category_size}, by one-year return`
                    : "By one-year return",
              } satisfies StatTile,
              {
                label: "Yearly swing",
                value: swing != null ? `${swing.toFixed(1)}%` : "-",
                note: "From daily moves",
              } satisfies StatTile,
              {
                label: "Deepest fall",
                value: fall != null ? `${fall.toFixed(1)}%` : "-",
                tone: fall != null && fall < 0 ? "down" : undefined,
                note: "From a peak, last 3 years",
              } satisfies StatTile,
            ]
          : []),
      ]
    : [];

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 md:px-6">
      <Link
        to="/funds"
        className="label-caps inline-flex items-center gap-1.5 text-muted transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden />
        All funds
      </Link>

      <div className="mt-4">
        <DataState loading={query.isLoading} error={query.error} onRetry={query.refetch}>
          {fund && rows && (
            <>
              <header className="border-b border-line pb-5">
                <div className="flex flex-wrap gap-1">
                  {tags.map((t) => (
                    <span
                      key={t}
                      className="border border-line px-1.5 py-0.5 text-[11px] font-medium text-muted"
                    >
                      {t}
                    </span>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
                  <div className="min-w-0">
                    <h1 className="font-display text-2xl font-semibold leading-tight tracking-[-0.01em] md:text-3xl">
                      {fund.name}
                    </h1>
                    {fund.fund_house && <p className="mt-1 text-sm text-muted">{fund.fund_house}</p>}
                  </div>
                  <div className="shrink-0 sm:text-right">
                    <p className="label-caps">NAV</p>
                    <p className="num text-3xl font-medium leading-none">
                      {fund.latest_nav != null ? fmtPrice(fund.latest_nav) : "-"}
                    </p>
                    {fund.nav_date && (
                      <p className="num mt-1 text-xs text-faint">{fmtDate(fund.nav_date)}</p>
                    )}
                  </div>
                </div>
              </header>

              <StatTiles className="mt-5" tiles={tiles} />

              <section className="mt-6 border border-line bg-surface">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-2.5">
                  <h2 className="label-caps">NAV history</h2>
                  <div className="flex flex-wrap gap-1" role="group" aria-label="Chart window">
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
                <div className={cn("px-5 py-4 transition-opacity", query.isFetching && "opacity-60")}>
                  {navs.length > 1 ? (
                    <NavChart points={navs} positive={chartPositive} />
                  ) : (
                    <p className="py-10 text-center text-sm text-muted">
                      Not enough stored NAVs to draw this window yet.
                    </p>
                  )}
                </div>
                {windowGrew != null && (
                  <p className="border-t border-line px-5 py-3 text-sm leading-relaxed">
                    <span className="num font-medium">{fmtRupees(START)}</span> put in on{" "}
                    {fmtDate(first.date)} was worth{" "}
                    <span className={cn("num font-semibold", chartPositive ? "text-up" : "text-down")}>
                      {fmtRupees(windowGrew)}
                    </span>{" "}
                    on {fmtDate(last.date)}
                    <span className="text-muted">, {spanInWords(first.date, last.date)} later.</span>
                  </p>
                )}
              </section>

              <div className="mt-6 grid gap-6 lg:grid-cols-2">
                <Card title="Returns">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="border-b border-line">
                        <th scope="col" className="label-caps px-5 py-2.5 text-left">Period</th>
                        <th scope="col" className="label-caps px-3 py-2.5 text-right">Return</th>
                        <th scope="col" className="label-caps px-5 py-2.5 text-right">
                          {fmtRupees(START)} became
                        </th>
                      </tr>
                    </thead>
                    <ReturnTable title="Under a year" note="Total change" rows={rows.short} />
                    <ReturnTable title="A year or more" note="Yearly rate" rows={rows.long} />
                  </table>
                </Card>

                <div className="space-y-6">
                  {fromDb && (
                    <Card title="The ride">
                      <ul className="divide-y divide-line text-sm leading-relaxed">
                        <li className="px-5 py-3">
                          {swing != null ? (
                            <>
                              Its yearly return has typically varied by about{" "}
                              <span className="num font-semibold">{swing.toFixed(0)}%</span> either
                              side of its average.
                            </>
                          ) : (
                            <span className="text-muted">Not enough history to measure its swings.</span>
                          )}
                        </li>
                        <li className="px-5 py-3">
                          {fall != null ? (
                            <>
                              At its worst in the last three years, {fmtRupees(START)} at the peak
                              fell to{" "}
                              <span className="num font-semibold text-down">
                                {fmtRupees(START * (1 + fall / 100))}
                              </span>
                              .
                            </>
                          ) : (
                            <span className="text-muted">Not enough history to measure its deepest fall.</span>
                          )}
                        </li>
                        <li className="px-5 py-3">
                          {pos && fund.category ? (
                            <>
                              Over the past year it did better than{" "}
                              <span className="num font-semibold">{Math.max(0, 100 - pos.topPct)}%</span>{" "}
                              of {fund.category} funds.
                            </>
                          ) : (
                            <span className="text-muted">No category rank yet.</span>
                          )}
                        </li>
                      </ul>
                    </Card>
                  )}

                  <Card title="About this fund">
                    <dl className="divide-y divide-line text-sm">
                      {(
                        [
                          ["Fund house", fund.fund_house ?? null],
                          ["Category", fund.category],
                          ["Launched", fund.launch_date ? fmtDate(fund.launch_date) : null],
                          ["AMFI code", fund.amfi_code],
                          ["ISIN", fund.isin ?? null],
                          [
                            "Stored NAVs",
                            fund.history_start && fund.history_end
                              ? `${fund.nav_points.toLocaleString("en-IN")}, ${fmtDate(fund.history_start)} to ${fmtDate(fund.history_end)}`
                              : String(fund.nav_points),
                          ],
                        ] as Array<[string, string | null]>
                      )
                        .filter(([, v]) => v)
                        .map(([label, value]) => (
                          <div key={label} className="flex items-baseline justify-between gap-4 px-5 py-2.5">
                            <dt className="shrink-0 text-muted">{label}</dt>
                            <dd className="num min-w-0 truncate text-right">{value}</dd>
                          </div>
                        ))}
                    </dl>
                  </Card>
                </div>
              </div>

              {/* Holdings: honest absence until portfolio disclosures are collected. */}
              <Card title="What it holds" className="mt-6">
                <div className="px-5 py-5">
                  <p className="text-sm font-semibold">Not collected yet</p>
                  <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted">
                    Fund houses publish what each fund holds once a month. When those files are
                    collected, this section will list the shares the fund owns with their
                    weights, each linking to its research page, and score the portfolio with the
                    same Quality, Valuation, Strength and Risk ratings used on stock pages.
                    Nothing is estimated in the meantime.
                  </p>
                </div>
              </Card>

              <p className="mt-4 max-w-3xl text-xs leading-relaxed text-faint">
                NAVs are daily values from AMFI (official), with earlier history from mfapi.in.
                Returns come from stored history only; a year or longer is a yearly rate. The
                rupee figures are arithmetic on those returns, before tax and exit charges, not a
                projection. Past performance is not indicative of future results. Not investment
                advice.
              </p>
            </>
          )}
        </DataState>
      </div>
    </div>
  );
}
