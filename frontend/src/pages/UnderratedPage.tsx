import * as React from "react";
import { Link } from "react-router-dom";
import { Check, ChevronDown, Minus, X } from "lucide-react";

import { SectionHeader } from "@/components/data/SectionHeader";
import { DataState } from "@/components/data/DataState";
import { StatTiles } from "@/components/data/StatTiles";
import { useUnderrated } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { UnderratedCheck, UnderratedItem } from "@/lib/types";

/**
 * Underrated gems: good businesses whose price assumes little and which the
 * market has not yet re-rated. The opposite of Strength, which finds what has
 * already risen. Four checks, every figure shown, so each name can be read
 * rather than trusted. A research screen: untested as a strategy (its frozen
 * monthly list on the track-record page is the test), and cheap companies can
 * be cheap for a reason (cyclical peak profits, a business in decline).
 */

type SortKey = "match" | "below_high" | "quality" | "strength";

const SORTS: Array<{ key: SortKey; label: string }> = [
  { key: "match", label: "Best match" },
  { key: "below_high", label: "Furthest below high" },
  { key: "quality", label: "Strongest business" },
  { key: "strength", label: "Least risen" },
];

/** Short names for the four checks, in the order the API returns them. */
const SHORT: Record<string, string> = {
  quality: "Business",
  expectations: "Price",
  valuation: "Peers",
  rerating: "Not risen",
};

function bare(symbol: string): string {
  return symbol.replace(/\.(NS|BO)$/, "");
}

function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? "-" : `${v.toFixed(digits)}%`;
}

function sortItems(items: UnderratedItem[], key: SortKey): UnderratedItem[] {
  if (key === "match") return items; // the server's order
  const pick = (i: UnderratedItem): number | null =>
    key === "below_high" ? i.from_high_pct : key === "quality" ? i.fundamental : i.strength;
  const asc = key !== "quality"; // most negative / lowest first, except quality
  return [...items].sort((a, b) => {
    const x = pick(a);
    const y = pick(b);
    if (x == null) return y == null ? 0 : 1; // missing figures last
    if (y == null) return -1;
    return asc ? x - y : y - x;
  });
}

/**
 * What the price needs against what the company grew, on one shared scale
 * (-10% to 40% a year, clamped). The hollow tick is the growth the price
 * needs; the filled bar runs from there to the growth the company delivered.
 */
function GrowthGap({ item }: { item: UnderratedItem }) {
  const { needed_growth_pct: needs, own_growth_pct: grew } = item;
  if (needs == null) return <span className="num text-sm text-faint">-</span>;
  const lo = -10;
  const hi = 40;
  const at = (v: number) => ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * 100;
  const a = at(needs);
  const b = grew == null ? a : at(grew);
  const ahead = grew != null && grew >= needs;
  return (
    <div className="min-w-0">
      <div className="relative h-3" aria-hidden>
        <span className="absolute inset-x-0 top-1/2 h-px bg-line" />
        <span className="absolute top-0 h-3 w-px bg-rule" style={{ left: `${at(0)}%` }} />
        {grew != null && (
          <span
            className="absolute top-1 h-1"
            style={{
              left: `${Math.min(a, b)}%`,
              width: `${Math.abs(b - a)}%`,
              background: ahead ? "var(--up)" : "var(--down)",
            }}
          />
        )}
        <span
          className="absolute top-0 h-3 w-0.5"
          style={{ left: `calc(${a}% - 1px)`, background: "var(--ink)" }}
        />
        {grew != null && (
          <span
            className="absolute top-0.5 size-2 rounded-full"
            style={{ left: `calc(${b}% - 4px)`, background: ahead ? "var(--up)" : "var(--down)" }}
          />
        )}
      </div>
      <p className="num mt-1 whitespace-nowrap text-xs text-muted">
        needs <span className="font-medium text-foreground">{pct(needs)}</span>
        <span className="mx-1 text-faint">·</span>
        grew <span className="font-medium text-foreground">{pct(grew, 0)}</span>
        {item.low_base && (
          <span title="From a very low starting profit" className="ml-0.5 text-faint">
            *
          </span>
        )}
      </p>
    </div>
  );
}

function CheckPill({ check }: { check: UnderratedCheck }) {
  const state = check.passed == null ? "unknown" : check.passed ? "pass" : "fail";
  const Icon = state === "pass" ? Check : state === "fail" ? X : Minus;
  return (
    <span
      title={`${check.label}: ${check.detail}`}
      className={cn(
        "inline-flex items-center gap-1 border px-1.5 py-0.5 text-[11px] leading-none",
        state === "pass" && "border-up/50 text-up",
        state === "fail" && "border-down/50 text-down",
        state === "unknown" && "border-line text-faint",
      )}
    >
      <Icon className="size-3" aria-hidden />
      <span className="sr-only">
        {state === "pass" ? "Passed" : state === "fail" ? "Failed" : "No data"}:
      </span>
      {SHORT[check.key] ?? check.label}
    </span>
  );
}

function Why({ item }: { item: UnderratedItem }) {
  return (
    <div className="space-y-2">
      <ul className="space-y-1.5 text-xs leading-relaxed">
        {item.checks.map((c) => (
          <li key={c.key} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
            <span className="w-40 shrink-0 font-medium">{c.label}</span>
            <span className="min-w-0 text-muted">
              <span
                className={cn(
                  "font-medium",
                  c.passed == null ? "text-faint" : c.passed ? "text-up" : "text-down",
                )}
              >
                {c.passed == null ? "No data" : c.passed ? "Pass" : "Fail"}
              </span>
              <span className="mx-1 text-faint">·</span>
              {c.detail}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-faint">
        Open the{" "}
        <Link to={`/stocks/${bare(item.symbol)}#expectations`} className="underline">
          stock page
        </Link>{" "}
        to read its valuation, risk and news before deciding anything: a price that assumes
        falling profits can mean a bargain, or profits at a cyclical peak.
      </p>
    </div>
  );
}

function ShareLink({ item }: { item: UnderratedItem }) {
  return (
    <Link to={`/stocks/${bare(item.symbol)}`} className="group block min-w-0">
      <span className="tkr block text-sm font-semibold group-hover:text-cobalt group-hover:underline dark:group-hover:text-cobalt-strong">
        {bare(item.symbol)}
      </span>
      <span className="block truncate text-xs text-muted">{item.name}</span>
    </Link>
  );
}

function WhyButton({ open, onClick }: { open: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={open}
      className="inline-flex items-center gap-1 text-xs font-medium text-cobalt hover:underline dark:text-cobalt-strong"
    >
      {open ? "Hide" : "Why"}
      <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} aria-hidden />
    </button>
  );
}

function Row({ item, rank }: { item: UnderratedItem; rank: number }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <tr className={cn("border-b border-line", !open && "hover:bg-surface-2/50")}>
        <td className="num w-10 py-3 pl-4 pr-1 text-xs text-faint">{rank}</td>
        <td className="max-w-56 px-3 py-3">
          <ShareLink item={item} />
          <span className="mt-0.5 block truncate text-[11px] text-faint">{item.sector ?? "-"}</span>
        </td>
        <td className="w-56 px-3 py-3">
          <GrowthGap item={item} />
        </td>
        <td className="num px-3 py-3 text-right text-sm">
          {item.fundamental != null ? item.fundamental.toFixed(0) : "-"}
        </td>
        <td className="num px-3 py-3 text-right text-sm">
          {item.strength != null ? item.strength.toFixed(0) : "-"}
        </td>
        <td className="num px-3 py-3 text-right text-sm">
          {item.from_high_pct != null ? `${item.from_high_pct.toFixed(0)}%` : "-"}
        </td>
        <td className="px-3 py-3">
          <div className="flex flex-wrap justify-end gap-1">
            {item.checks.map((c) => (
              <CheckPill key={c.key} check={c} />
            ))}
          </div>
        </td>
        <td className="py-3 pl-2 pr-4 text-right">
          <WhyButton open={open} onClick={() => setOpen((v) => !v)} />
        </td>
      </tr>
      {open && (
        <tr className="border-b border-line bg-surface-2">
          <td />
          <td colSpan={7} className="px-3 py-3">
            <Why item={item} />
          </td>
        </tr>
      )}
    </>
  );
}

/** Phone layout: one card a share, the same figures stacked. */
function Card({ item, rank }: { item: UnderratedItem; rank: number }) {
  const [open, setOpen] = React.useState(false);
  return (
    <li className="border-b border-line p-4 last:border-b-0">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 gap-2">
          <span className="num pt-0.5 text-xs text-faint">{rank}</span>
          <div className="min-w-0">
            <ShareLink item={item} />
            <span className="mt-0.5 block truncate text-[11px] text-faint">{item.sector ?? "-"}</span>
          </div>
        </div>
        <WhyButton open={open} onClick={() => setOpen((v) => !v)} />
      </div>
      <div className="mt-3">
        <GrowthGap item={item} />
      </div>
      <dl className="num mt-3 grid grid-cols-3 gap-2 text-xs">
        {[
          ["Quality", item.fundamental != null ? item.fundamental.toFixed(0) : "-"],
          ["Strength", item.strength != null ? item.strength.toFixed(0) : "-"],
          ["From high", item.from_high_pct != null ? `${item.from_high_pct.toFixed(0)}%` : "-"],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="label-caps">{label}</dt>
            <dd className="mt-0.5 text-sm font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 flex flex-wrap gap-1">
        {item.checks.map((c) => (
          <CheckPill key={c.key} check={c} />
        ))}
      </div>
      {open && (
        <div className="mt-3 border-t border-line pt-3">
          <Why item={item} />
        </div>
      )}
    </li>
  );
}

const selectClass = "min-w-0 max-w-full border border-line bg-surface px-2 py-1 text-xs";

export default function UnderratedPage() {
  const [minChecks, setMinChecks] = React.useState(4);
  const [sector, setSector] = React.useState("");
  const [sort, setSort] = React.useState<SortKey>("match");
  // The explainer starts open where there is room and folded on a phone.
  const [checksOpen, setChecksOpen] = React.useState(
    () => typeof window === "undefined" || !window.matchMedia || window.matchMedia("(min-width: 640px)").matches,
  );
  const query = useUnderrated(minChecks);
  const data = query.data;
  const t = data?.thresholds;

  const sectors = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const i of data?.items ?? []) {
      if (i.sector) counts.set(i.sector, (counts.get(i.sector) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [data]);

  // A sector picked under one tab may not exist under the other.
  React.useEffect(() => {
    if (sector && !sectors.some(([s]) => s === sector)) setSector("");
  }, [sector, sectors]);

  const shown = React.useMemo(
    () =>
      sortItems(
        (data?.items ?? []).filter((i) => !sector || i.sector === sector),
        sort,
      ),
    [data, sector, sort],
  );
  const available = data ? (minChecks === 4 ? data.matches : data.matches + data.near_misses) : 0;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 md:px-6">
      <SectionHeader kicker="Screener" title="Underrated gems" />
      <p className="max-w-3xl text-sm leading-relaxed text-muted">
        Strength finds what has already risen, so part of the move is behind it. This is the
        opposite: companies in good shape whose price assumes little and which the market has not
        yet re-rated. It is a list of names to look into, not a buy signal. It has not been
        tested as a strategy; each month's top 20 is saved on the{" "}
        <Link to="/track-record" className="underline">
          track record
        </Link>{" "}
        page so it can be judged against the average share.
      </p>

      {data && (
        <StatTiles
          className="mt-6"
          tiles={[
            { label: "Pass all four", value: String(data.matches), tone: "up" },
            { label: "Pass three", value: String(data.near_misses) },
            { label: "Scanned", value: data.scanned.toLocaleString("en-IN") },
          ]}
        />
      )}

      {t && (
        <details className="group mt-4 border border-line bg-surface" open={checksOpen} onToggle={(e) => setChecksOpen(e.currentTarget.open)}>
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-2.5">
            <span className="label-caps">The four checks</span>
            <ChevronDown className="size-3.5 text-muted transition-transform group-open:rotate-180" aria-hidden />
          </summary>
          <ol className="grid gap-px border-t border-line bg-line text-xs leading-relaxed sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Good business", `Fundamental score ${t.min_fundamental}+ and solvency ${t.min_solvency}+.`],
              [
                "Price assumes little",
                `The yearly earnings growth the price needs for ten years is ${t.max_needed_growth_pct}% or less, and the company grew at least ${t.min_growth_gap_points} points faster.`,
              ],
              ["Cheap against peers", "Valued below its industry peers."],
              [
                "Not yet re-rated",
                `Strength ${t.max_strength} or below and at least ${t.min_below_high_pct}% under its one-year high.`,
              ],
            ].map(([title, body], i) => (
              <li key={title} className="flex gap-3 bg-surface p-4">
                <span className="num text-lg font-medium leading-none text-faint">{i + 1}</span>
                <span>
                  <span className="block font-semibold">{title}</span>
                  <span className="mt-1 block text-muted">{body}</span>
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="How many checks">
          {(
            [
              [4, "All four checks"],
              [3, "Three or more"],
            ] as const
          ).map(([n, label]) => (
            <button
              key={n}
              type="button"
              role="tab"
              aria-selected={minChecks === n}
              onClick={() => setMinChecks(n)}
              className={cn(
                "border px-3 py-1 text-xs font-medium transition-colors",
                minChecks === n
                  ? "border-cobalt bg-surface-2 text-foreground"
                  : "border-line text-muted hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="sr-only" htmlFor="underrated-sector">
          Sector
        </label>
        <select
          id="underrated-sector"
          value={sector}
          onChange={(e) => setSector(e.target.value)}
          className={selectClass}
        >
          <option value="">All sectors</option>
          {sectors.map(([s, n]) => (
            <option key={s} value={s}>
              {s} ({n})
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="underrated-sort">
          Sort
        </label>
        <select
          id="underrated-sort"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          className={selectClass}
        >
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              Sort: {s.label}
            </option>
          ))}
        </select>
        {data && data.items.length > 0 && (
          <p className="num ml-auto text-xs text-muted">
            {shown.length} shown
            {available > data.items.length ? ` · top ${data.items.length} of ${available}` : ""}
          </p>
        )}
      </div>

      <div className="mt-4">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          empty={Boolean(data) && shown.length === 0}
          emptyTitle="Nothing passes right now"
          emptyMessage={
            sector
              ? "No share in this sector passes. Try all sectors."
              : "No share passes this many checks today. Try three or more."
          }
        >
          {shown.length > 0 && (
            <>
              <ul className="border border-line bg-surface md:hidden">
                {shown.map((item, i) => (
                  <Card key={item.symbol} item={item} rank={i + 1} />
                ))}
              </ul>
              <div className="hidden overflow-x-auto border border-line bg-surface md:block">
                <table className="w-full min-w-[860px] border-collapse text-left">
                  <thead>
                    <tr className="border-b border-line">
                      <th scope="col" className="label-caps py-3 pl-4 pr-1">#</th>
                      <th scope="col" className="label-caps px-3 py-3">Share</th>
                      <th
                        scope="col"
                        className="label-caps px-3 py-3"
                        title="Yearly earnings growth the price needs, against the company's own growth"
                      >
                        Price needs vs it grew
                      </th>
                      <th scope="col" className="label-caps px-3 py-3 text-right" title="Fundamental score, 0 to 100">
                        Quality
                      </th>
                      <th scope="col" className="label-caps px-3 py-3 text-right" title="One-year price strength, 0 to 100">
                        Strength
                      </th>
                      <th scope="col" className="label-caps px-3 py-3 text-right" title="Gap to the one-year high">
                        From high
                      </th>
                      <th scope="col" className="label-caps px-3 py-3 text-right">Checks</th>
                      <th scope="col" className="py-3 pl-2 pr-4" />
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((item, i) => (
                      <Row key={item.symbol} item={item} rank={i + 1} />
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </DataState>
      </div>

      <p className="mt-4 max-w-3xl text-xs leading-relaxed text-faint">
        The bar runs from the growth the price needs (the tick) to the growth the company
        delivered (the dot), on a scale of -10% to 40% a year. * Growth from a very low starting
        profit; it counts as at most 40% when ranking. Best match ranks by checks passed, then by
        how far the company's growth is ahead of what the price needs. Cheap companies can be
        cheap for a reason. Not investment advice.
      </p>
    </div>
  );
}
