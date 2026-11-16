import { useExpectations } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { CollapsibleSection } from "@/components/stock/CollapsibleSection";
import { fmtDate, fmtMarketCap } from "@/lib/format";
import type { ExpectationsResponse } from "@/lib/types";

/**
 * ExpectationsSection ("growth built into the price"): a reverse
 * discounted-earnings model, computed by the backend. Instead of a "fair
 * value" it states the yearly profit growth today's market value needs for
 * ten years, then sets it beside what the company actually delivered and how
 * often listed companies have grown that fast. Loss-making companies get a
 * reason, not a number. Copy is written for a first-time reader: no "you",
 * no finance shorthand, one idea per sentence.
 */

function pct(value: number | null | undefined, digits = 1): string {
  return value == null ? "-" : `${value.toFixed(digits)}%`;
}

function central(e: ExpectationsResponse) {
  return e.implied.find((i) => i.discount_rate_pct === 12) ?? e.implied[1] ?? null;
}

/** "grow about 6.9% a year" / "shrink about 2.0% a year", for use after "has to" or "must". */
function growthText(growth: number, bound: string | null): string {
  if (bound === "below") return `shrink by more than ${Math.abs(growth).toFixed(0)}% a year`;
  if (bound === "above") return `grow by more than ${growth.toFixed(0)}% a year`;
  if (growth < 0) return `shrink about ${Math.abs(growth).toFixed(1)}% a year`;
  return `grow about ${growth.toFixed(1)}% a year`;
}

export function expectationsSummary(e: ExpectationsResponse | undefined): string | null {
  if (!e || e.status !== "ok") return null;
  const c = central(e);
  if (!c) return null;
  if (!c.bound && c.growth_pct <= 0) {
    return "The price holds up even if profit stops growing";
  }
  return `Profit must ${growthText(c.growth_pct, c.bound)} for ${e.years} years to justify the price`;
}

const REASONS: Record<string, string> = {
  no_market_value: "There is no stored market value for this company yet.",
  no_earnings: "There are no stored profit figures for this company yet.",
  loss_making:
    "The company made a loss over its latest year. This check starts from current profit and asks how fast it has to grow, so it cannot be worked out for a loss-making company.",
};

/** Within this many points, needed and delivered growth read as "about the same". */
const CLOSE_POINTS = 2;

/** One plain sentence comparing the growth the price needs with what was delivered. */
function verdict(e: ExpectationsResponse): string | null {
  const c = central(e);
  const own = e.own.earnings_growth_pct;
  if (!c || c.bound) return null;
  const record =
    own == null
      ? null
      : `Over the last ${e.own.years} years its profit ${own < 0 ? "fell" : "grew"} ${pct(Math.abs(own))} a year.`;
  if (c.growth_pct <= 0) {
    return `${record ? record + " " : ""}The price does not depend on any growth: it is set as if profit will shrink from here.`;
  }
  if (record == null) {
    return "There is no clean profit growth figure to compare this with (a loss year or a missing year in the record).";
  }
  const gap = c.growth_pct - own!;
  if (gap > CLOSE_POINTS) {
    return `${record} The price is counting on faster growth than the company has recently delivered.`;
  }
  if (gap < -CLOSE_POINTS) {
    return `${record} That is faster than the price needs, so the price holds up even if growth slows.`;
  }
  return `${record} The price needs about the same pace, kept up for ${e.years} years.`;
}

export function ExpectationsSection({ symbol }: { symbol: string }) {
  const query = useExpectations(symbol);
  const e = query.data;
  const c = e ? central(e) : null;
  const others = e && c ? e.implied.filter((i) => i !== c) : [];

  return (
    <CollapsibleSection
      id="expectations"
      kicker="Expectations"
      title="Growth built into the price"
      summary={expectationsSummary(e)}
    >
      <DataState loading={query.isLoading} error={query.error} onRetry={query.refetch}>
        {e && e.status !== "ok" && (
          <p className="border border-line bg-surface px-5 py-4 text-sm leading-relaxed text-muted">
            {REASONS[e.reason ?? ""] ?? "Not enough data to work this out."}
          </p>
        )}
        {e && e.status === "ok" && c && (
          <>
            <p className="max-w-3xl text-base leading-relaxed">
              The company is valued at{" "}
              <span className="num font-medium">{fmtMarketCap(e.market_value)}</span>, which is{" "}
              <span className="num font-medium">{e.pe?.toFixed(1)}</span> times the profit it
              made in its latest year. For that price to be justified, profit has to{" "}
              <span className="font-semibold">
                {growthText(c.growth_pct, c.bound)} for the next {e.years} years
              </span>
              .
            </p>
            {verdict(e) && <p className="mt-2 max-w-3xl text-sm text-muted">{verdict(e)}</p>}

            <div className="mt-6 grid gap-px border border-line bg-line @xl:grid-cols-3">
              <Tile
                label="Growth the price needs"
                value={c.bound ? (c.bound === "above" ? `>${c.growth_pct.toFixed(0)}%` : `<${c.growth_pct.toFixed(0)}%`) : pct(c.growth_pct)}
                note={`Profit growth a year, for ${e.years} years, for the share to return ${c.discount_rate_pct}% a year (a common target for Indian shares).${
                  others.length
                    ? ` For a return of ${others
                        .map((i) => `${i.discount_rate_pct}% it is ${pct(i.growth_pct)}`)
                        .join("; for ")}.`
                    : ""
                }`}
              />
              <Tile
                label="Growth the company delivered"
                value={pct(e.own.earnings_growth_pct)}
                note={
                  e.own.years
                    ? `Profit growth a year over the last ${e.own.years} years (${fmtDate(e.own.from_year_end)} to ${fmtDate(e.own.to_year_end)}). Sales grew ${pct(e.own.revenue_growth_pct)} a year.`
                    : "Fewer than two full years of results are stored."
                }
              />
              <Tile
                label="How often companies manage it"
                value={pct(e.base_rate_pct, 0)}
                note={
                  e.base_rate_pct != null
                    ? `Across ${e.base_rate_windows.toLocaleString("en-IN")} ${e.base_rate_years}-year periods of listed companies, profit grew at least ${pct(c.growth_pct)} a year in this share of them. Keeping it up for ${e.years} years is much rarer.`
                    : "Too few company records to say."
                }
              />
            </div>

            <details className="mt-5 text-xs leading-relaxed text-faint">
              <summary className="cursor-pointer text-muted">How this is worked out</summary>
              <p className="mt-2 max-w-3xl">
                A share is worth the profit the company will earn in future, with later profit
                counting for less. The starting point is the profit of the{" "}
                {e.earnings_basis === "last_4_quarters" ? "last four quarters" : "latest full year"}{" "}
                (to {fmtDate(e.earnings_period_end)}). It is assumed to grow at one steady rate
                for {e.years} years and at {e.terminal_growth_pct.toFixed(0)}% a year after that
                (about India&rsquo;s long-run growth). The figure shown is the growth rate at
                which those future profits add up to today&rsquo;s market value, for an investor
                who wants the stated yearly return. It treats all profit as cash the owners
                could take out, so a company that must reinvest most of its profit to grow
                needs more than this. It shows what the price depends on. It is not a forecast
                or a recommendation.
              </p>
            </details>
          </>
        )}
      </DataState>
    </CollapsibleSection>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="bg-surface p-5">
      <p className="label-caps">{label}</p>
      <p className="num mt-1.5 text-2xl font-medium">{value}</p>
      {note && <p className="mt-2 text-xs leading-relaxed text-muted">{note}</p>}
    </div>
  );
}
