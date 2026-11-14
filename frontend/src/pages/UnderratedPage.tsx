import * as React from "react";
import { Link } from "react-router-dom";
import { Check, CircleHelp, X } from "lucide-react";

import { SectionHeader } from "@/components/data/SectionHeader";
import { DataState } from "@/components/data/DataState";
import { useUnderrated } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { UnderratedCheck, UnderratedItem } from "@/lib/types";

/**
 * Underrated: good businesses whose price assumes little and which the market
 * has not yet re-rated. The opposite of Strength, which finds what has
 * already risen. Four checks, every figure shown, so each name can be read
 * rather than trusted. A research screen: untested as a strategy (its frozen
 * monthly list on the track-record page is the test), and cheap companies can
 * be cheap for a reason (cyclical peak profits, a business in decline).
 */

function bare(symbol: string): string {
  return symbol.replace(/\.(NS|BO)$/, "");
}

function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? "-" : `${v.toFixed(digits)}%`;
}

function Mark({ check }: { check: UnderratedCheck }) {
  const Icon = check.passed == null ? CircleHelp : check.passed ? Check : X;
  return (
    <span
      title={`${check.label}: ${check.detail}`}
      className={cn(
        "inline-flex size-6 items-center justify-center border",
        check.passed == null
          ? "border-line text-faint"
          : check.passed
            ? "border-up text-up"
            : "border-line text-faint",
      )}
    >
      <Icon className="size-3.5" aria-label={check.passed ? "passed" : check.passed == null ? "no data" : "failed"} />
    </span>
  );
}

function Row({ item }: { item: UnderratedItem }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <tr className="border-b border-line">
        <td className="px-4 py-2.5">
          <Link to={`/stocks/${bare(item.symbol)}`} className="group block">
            <span className="block text-sm font-medium group-hover:text-cobalt group-hover:underline">
              {bare(item.symbol)}
            </span>
            <span className="block max-w-56 truncate text-xs text-faint">{item.name}</span>
          </Link>
        </td>
        <td className="hidden px-3 py-2.5 text-xs text-muted md:table-cell">{item.sector ?? "-"}</td>
        <td className="num px-3 py-2.5 text-right text-sm">{pct(item.needed_growth_pct)}</td>
        <td className="num px-3 py-2.5 text-right text-sm">
          {pct(item.own_growth_pct, 0)}
          {item.low_base && (
            <span title="From a very low starting profit" className="ml-1 text-xs text-faint">
              *
            </span>
          )}
        </td>
        <td className="num hidden px-3 py-2.5 text-right text-sm sm:table-cell">
          {item.from_high_pct != null ? `${item.from_high_pct.toFixed(0)}%` : "-"}
        </td>
        <td className="px-3 py-2.5">
          <div className="flex justify-end gap-1">
            {item.checks.map((c) => (
              <Mark key={c.key} check={c} />
            ))}
          </div>
        </td>
        <td className="px-3 py-2.5 text-right">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="text-xs font-medium text-cobalt hover:underline"
          >
            {open ? "Hide" : "Why"}
          </button>
        </td>
      </tr>
      {open && (
        <tr className="border-b border-line bg-surface-2">
          <td colSpan={7} className="px-4 py-3">
            <ul className="space-y-1 text-xs leading-relaxed">
              {item.checks.map((c) => (
                <li key={c.key} className="flex gap-2">
                  <span className="w-36 shrink-0 font-medium">{c.label}</span>
                  <span className={cn("min-w-0", c.passed ? "text-foreground" : "text-muted")}>
                    {c.passed == null ? "No data. " : c.passed ? "Pass. " : "Fail. "}
                    {c.detail}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-faint">
              Open the{" "}
              <Link to={`/stocks/${bare(item.symbol)}#expectations`} className="underline">
                stock page
              </Link>{" "}
              to read its valuation, risk and news before deciding anything: a price that assumes
              falling profits can mean a bargain, or profits at a cyclical peak.
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

export default function UnderratedPage() {
  const [minChecks, setMinChecks] = React.useState(4);
  const query = useUnderrated(minChecks);
  const data = query.data;
  const t = data?.thresholds;

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <SectionHeader
        kicker="Screener"
        title="Underrated"
        aside={
          data ? (
            <p className="num text-xs text-muted">
              {data.matches} match all four · {data.near_misses} match three · {data.scanned}{" "}
              scanned
            </p>
          ) : undefined
        }
      />
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

      {t && (
        <ol className="mt-6 grid gap-px border border-line bg-line text-xs leading-relaxed sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["1. Good business", `Fundamental score ${t.min_fundamental}+ and solvency ${t.min_solvency}+.`],
            [
              "2. Price assumes little",
              `The yearly earnings growth the price needs for ten years is ${t.max_needed_growth_pct}% or less, and the company grew at least ${t.min_growth_gap_points} points faster.`,
            ],
            ["3. Cheap against peers", "Valued below its industry peers."],
            [
              "4. Not yet re-rated",
              `Strength ${t.max_strength} or below and at least ${t.min_below_high_pct}% under its one-year high.`,
            ],
          ].map(([title, body]) => (
            <li key={title} className="bg-surface p-4">
              <p className="font-semibold">{title}</p>
              <p className="mt-1 text-muted">{body}</p>
            </li>
          ))}
        </ol>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-2" role="tablist" aria-label="How many checks">
        {[
          [4, "All four checks"],
          [3, "Three or more"],
        ].map(([n, label]) => (
          <button
            key={n}
            type="button"
            role="tab"
            aria-selected={minChecks === n}
            onClick={() => setMinChecks(n as number)}
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

      <div className="mt-4">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          empty={Boolean(data) && data?.items.length === 0}
          emptyTitle="Nothing passes right now"
          emptyMessage="No share passes this many checks today. Try three or more."
        >
          {data && data.items.length > 0 && (
            <div className="overflow-x-auto border border-line bg-surface">
              <table className="w-full min-w-[640px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-line">
                    <th scope="col" className="label-caps px-4 py-3">Share</th>
                    <th scope="col" className="label-caps hidden px-3 py-3 md:table-cell">Sector</th>
                    <th scope="col" className="label-caps px-3 py-3 text-right" title="Yearly earnings growth the price needs">
                      Price needs
                    </th>
                    <th scope="col" className="label-caps px-3 py-3 text-right" title="The company's own yearly earnings growth">
                      It grew
                    </th>
                    <th scope="col" className="label-caps hidden px-3 py-3 text-right sm:table-cell">
                      From high
                    </th>
                    <th scope="col" className="label-caps px-3 py-3 text-right">Checks</th>
                    <th scope="col" className="px-3 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <Row key={item.symbol} item={item} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataState>
      </div>

      <p className="mt-4 max-w-3xl text-xs leading-relaxed text-faint">
        * Growth from a very low starting profit; it counts as at most 40% when ranking. Ranked by
        checks passed, then by how far the company's growth is ahead of what the price needs.
        Cheap companies can be cheap for a reason. Not investment advice.
      </p>
    </div>
  );
}
