import * as React from "react";
import { Link } from "react-router-dom";

import { SectionHeader } from "@/components/data/SectionHeader";
import { DataState } from "@/components/data/DataState";
import { TimeSeriesChart, type TimeSeriesLine } from "@/components/chart/TimeSeriesChart";
import { useTrackRecord } from "@/lib/hooks";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { FrozenList, StrengthBacktest } from "@/lib/types";

/**
 * TrackRecord: the ratings keep score in public. Two parts:
 *  1. Frozen lists. On the first trading night of each month the top 20
 *     shares by Alpha and by Strength are written down and never changed;
 *     each list is then followed from the next day's close against the
 *     average share on the list and the NIFTY 50.
 *  2. The Strength back-test: the same top-20 rule applied month by month
 *     over about nine years of prices, against the average share.
 * The page states its own limits (survivor bias, no costs, a back-test
 * flatters) next to the numbers, not in a footnote elsewhere.
 */

const RATING_NAME: Record<string, string> = { alpha: "Alpha", strength: "Strength" };

function signed(v: number | null | undefined, digits = 1): string {
  if (v == null) return "-";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function bare(symbol: string): string {
  return symbol.replace(/\.(NS|BO)$/, "");
}

export default function TrackRecordPage() {
  const query = useTrackRecord();
  const data = query.data;

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <SectionHeader kicker="Accountability" title="Track record" />
      <p className="max-w-3xl text-sm leading-relaxed text-muted">
        Every rating on this site is a claim about which shares are in better shape. This page
        keeps score in public: what the top-rated shares did next, against the average share.
      </p>

      <DataState loading={query.isLoading} error={query.error} onRetry={query.refetch}>
        {data && (
          <div className="mt-10 space-y-16">
            <FrozenLists lists={data.lists} latest={data.latest_close} indexName={data.index_name} />
            <Backtest bt={data.backtest} />
          </div>
        )}
      </DataState>
    </div>
  );
}

function FrozenLists({
  lists,
  latest,
  indexName,
}: {
  lists: FrozenList[];
  latest: string | null;
  indexName: string;
}) {
  return (
    <section>
      <p className="label-caps">Live record</p>
      <h2 className="mt-1 font-display text-2xl font-semibold">The monthly lists, frozen</h2>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
        On the first trading night of each month the 20 highest-rated shares by Alpha and by
        Strength are written down and never edited. Each list is followed from the next day's
        close{latest ? `, to ${fmtDate(latest)}` : ""}: an equal amount in each share, no costs.
      </p>

      {lists.length === 0 ? (
        <p className="mt-6 border border-line bg-surface px-5 py-4 text-sm text-muted">
          The first lists are written on the next nightly run. They will appear here, and from
          then on nothing on them can change.
        </p>
      ) : (
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {lists.map((l) => (
            <ListCard key={`${l.list_date}-${l.rating}`} list={l} indexName={indexName} />
          ))}
        </div>
      )}
    </section>
  );
}

function ListCard({ list, indexName }: { list: FrozenList; indexName: string }) {
  const [open, setOpen] = React.useState(false);
  const ahead =
    list.return_pct != null && list.list_average_pct != null
      ? list.return_pct - list.list_average_pct
      : null;
  return (
    <div className="border border-line bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium">
          {RATING_NAME[list.rating] ?? list.rating} top {list.holdings.length}
        </p>
        <p className="num text-xs text-faint">frozen {fmtDate(list.list_date)}</p>
      </div>
      {list.started ? (
        <dl className="mt-4 grid grid-cols-3 gap-3">
          <Figure label="The list" value={signed(list.return_pct)} strong />
          <Figure label="Average share" value={signed(list.list_average_pct)} />
          <Figure label={indexName} value={signed(list.index_pct)} />
        </dl>
      ) : (
        <p className="mt-4 text-sm text-muted">Starts counting from the next trading day's close.</p>
      )}
      {ahead != null && (
        <p className={cn("mt-3 text-xs", ahead >= 0 ? "text-up" : "text-down")}>
          {ahead >= 0 ? "Ahead of" : "Behind"} the average share by {Math.abs(ahead).toFixed(1)} points so far.
        </p>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mt-4 text-xs font-medium text-cobalt hover:underline"
      >
        {open ? "Hide the shares" : "Show the shares"}
      </button>
      {open && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-muted">
                <th className="py-1 pr-2 font-normal">#</th>
                <th className="py-1 pr-2 font-normal">Share</th>
                <th className="py-1 pr-2 text-right font-normal">Score</th>
                <th className="py-1 text-right font-normal">Since</th>
              </tr>
            </thead>
            <tbody>
              {list.holdings.map((h) => (
                <tr key={h.symbol} className="border-t border-line">
                  <td className="num py-1.5 pr-2 text-faint">{h.rank}</td>
                  <td className="py-1.5 pr-2">
                    <Link to={`/stocks/${bare(h.symbol)}`} className="hover:underline">
                      {bare(h.symbol)}
                    </Link>
                    {h.name && <span className="ml-1.5 text-faint">{h.name}</span>}
                  </td>
                  <td className="num py-1.5 pr-2 text-right">{h.score?.toFixed(0) ?? "-"}</td>
                  <td
                    className={cn(
                      "num py-1.5 text-right",
                      h.return_pct != null && (h.return_pct >= 0 ? "text-up" : "text-down"),
                    )}
                  >
                    {signed(h.return_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Figure({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd className={cn("num mt-0.5 text-lg", strong ? "font-semibold" : "font-medium")}>{value}</dd>
    </div>
  );
}

function Backtest({ bt }: { bt: StrengthBacktest | null }) {
  const lines = React.useMemo<TimeSeriesLine[]>(() => {
    if (!bt) return [];
    return [
      {
        key: "top",
        label: `Strength top ${bt.top_n}`,
        color: "--cobalt",
        width: 2,
        data: bt.curve.map((p) => ({ time: p.month, value: p.top * 100 })),
      },
      {
        key: "list",
        label: "Average share",
        color: "--faint",
        width: 2,
        data: bt.curve.map((p) => ({ time: p.month, value: p.list * 100 })),
      },
    ];
  }, [bt]);

  return (
    <section>
      <p className="label-caps">Back-test</p>
      <h2 className="mt-1 font-display text-2xl font-semibold">Strength, month by month</h2>
      {!bt ? (
        <p className="mt-6 border border-line bg-surface px-5 py-4 text-sm text-muted">
          The back-test is rebuilt once a week from about ten years of prices. It has not run yet.
        </p>
      ) : (
        <>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
            Every month from {fmtDate(bt.from_)} to {fmtDate(bt.to)}, the {bt.top_n} shares with the
            highest Strength, held for one month from the next day's close, then replaced. Against
            the average of all {bt.shares.toLocaleString("en-IN")} shares over the same days.
            Strength uses prices only, so each month's list is exactly what the rating would have
            said that day.
          </p>

          <div className="mt-6 grid gap-px border border-line bg-line sm:grid-cols-3">
            <Stat label={`Strength top ${bt.top_n}`} value={signed(bt.top_yearly)} note="a year, compounded" />
            <Stat label="Average share" value={signed(bt.list_yearly)} note="a year, compounded" />
            <Stat
              label="Months ahead"
              value={`${bt.months_beat} of ${bt.months_count}`}
              note={`${((bt.months_beat / bt.months_count) * 100).toFixed(0)}% of months`}
            />
          </div>

          <div className="mt-6 border border-line bg-surface p-5">
            <p className="label-caps mb-3">Growth of ₹100</p>
            <TimeSeriesChart lines={lines} height={260} valueFormatter={(v) => `₹${v.toFixed(0)}`} />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Quintiles values={bt.quintiles} />
            <div className="overflow-x-auto border border-line bg-surface p-5">
              <p className="label-caps">Year by year</p>
              <p className="mb-3 mt-1 text-xs text-muted">Green: the top {bt.top_n} beat the average share that year.</p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted">
                    <th className="py-1 font-normal">Year</th>
                    <th className="py-1 text-right font-normal">Top {bt.top_n}</th>
                    <th className="py-1 text-right font-normal">Average</th>
                  </tr>
                </thead>
                <tbody>
                  {bt.years.map((y) => (
                    <tr key={y.year} className="border-t border-line">
                      <td className="num py-1.5">
                        {y.year}
                        {y.months < 12 && <span className="ml-1 text-xs text-faint">({y.months} mo)</span>}
                      </td>
                      <td className={cn("num py-1.5 text-right", y.top >= y.list ? "text-up" : "text-down")}>
                        {signed(y.top)}
                      </td>
                      <td className="num py-1.5 text-right text-muted">{signed(y.list)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-6 max-w-3xl space-y-2 text-xs leading-relaxed text-faint">
            <p>
              <span className="font-semibold text-muted">Why this flatters. </span>
              The shares are today's 1,000 largest, so companies that shrank or delisted over the
              decade are missing; that lifts the average share too, which is why it shows over 20%
              a year. Strength was designed with this kind of history in view, so a back-test is
              its best case. There are no trading costs or taxes, and the top 20 change often.
            </p>
            <p>
              The frozen lists above are the real test: they cannot be tuned after the fact.
              Rebuilt weekly (as of {fmtDate(bt.asof)}). Past results do not predict future ones.
            </p>
          </div>
        </>
      )}
    </section>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="bg-surface p-5">
      <p className="label-caps">{label}</p>
      <p className="num mt-1.5 text-2xl font-medium">{value}</p>
      <p className="mt-1 text-xs text-muted">{note}</p>
    </div>
  );
}

function Quintiles({ values }: { values: (number | null)[] }) {
  const max = Math.max(1, ...values.map((v) => Math.abs(v ?? 0)));
  return (
    <div className="border border-line bg-surface p-5">
      <p className="label-caps">Does the rating sort shares?</p>
      <p className="mt-1 text-xs text-muted">
        The whole list split into fifths by Strength each month: average yearly return of each fifth.
      </p>
      <div className="mt-4 space-y-2">
        {values.map((v, i) => (
          <div key={i} className="flex items-center gap-3 text-xs">
            <span className="w-24 shrink-0 text-muted">
              {i === 0 ? "Weakest fifth" : i === values.length - 1 ? "Strongest fifth" : `Fifth ${i + 1}`}
            </span>
            <div className="relative h-3 min-w-0 flex-1 bg-surface-2">
              <div
                className={cn("absolute inset-y-0 left-0", i === values.length - 1 ? "bg-cobalt" : "bg-faint")}
                style={{ width: `${(Math.max(0, v ?? 0) / max) * 100}%` }}
              />
            </div>
            <span className="num w-14 shrink-0 text-right">{signed(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
