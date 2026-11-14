import { useExpectations } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { CollapsibleSection } from "@/components/stock/CollapsibleSection";
import { fmtDate, fmtMarketCap } from "@/lib/format";
import type { ExpectationsResponse } from "@/lib/types";

/**
 * ExpectationsSection ("what the price assumes"): a reverse discounted-
 * earnings model, computed by the backend. Instead of a "fair value" it
 * states the yearly earnings growth today's market value needs for ten
 * years, then sets it beside the company's own record and how often any
 * listed company grew that fast. Loss-making companies get a reason, not
 * a number.
 */

function pct(value: number | null | undefined, digits = 1): string {
  return value == null ? "-" : `${value.toFixed(digits)}%`;
}

function central(e: ExpectationsResponse) {
  return e.implied.find((i) => i.discount_rate_pct === 12) ?? e.implied[1] ?? null;
}

function growthText(growth: number, bound: string | null): string {
  if (bound === "below") return `earnings shrinking by more than ${Math.abs(growth).toFixed(0)}% a year`;
  if (bound === "above") return `earnings growing by more than ${growth.toFixed(0)}% a year`;
  if (growth < 0) return `earnings shrinking about ${Math.abs(growth).toFixed(1)}% a year`;
  return `earnings growing about ${growth.toFixed(1)}% a year`;
}

export function expectationsSummary(e: ExpectationsResponse | undefined): string | null {
  if (!e || e.status !== "ok") return null;
  const c = central(e);
  if (!c) return null;
  return `The price assumes ${growthText(c.growth_pct, c.bound)} for ${e.years} years`;
}

const REASONS: Record<string, string> = {
  no_market_value: "There is no stored market value for this company yet.",
  no_earnings: "There are no stored earnings for this company yet.",
  loss_making:
    "The company made a loss over its latest year, so there is no growth rate that turns today's earnings into today's price. The model needs profits to start from.",
};

/** Plain-language comparison of the needed growth with the company's record. */
function verdict(e: ExpectationsResponse): string | null {
  const c = central(e);
  const own = e.own.earnings_growth_pct;
  if (!c || c.bound) return null;
  if (c.growth_pct <= 0) {
    return "The price asks for no growth at all: it is priced as if profits will shrink.";
  }
  if (own == null) {
    return "There is no clean earnings growth figure to compare with (a loss year or a missing year in the record).";
  }
  const gap = c.growth_pct - own;
  if (gap <= -5) {
    return `Its recent record (${pct(own)} a year) is well ahead of what the price asks. The question is whether that pace can last ten years.`;
  }
  if (gap < 5) {
    return `The price asks for about the pace the company has recently managed (${pct(own)} a year), kept up for ten years.`;
  }
  return `The price asks for faster growth than the company has recently managed (${pct(own)} a year), and for ten years.`;
}

export function ExpectationsSection({ symbol }: { symbol: string }) {
  const query = useExpectations(symbol);
  const e = query.data;
  const c = e ? central(e) : null;

  return (
    <CollapsibleSection
      id="expectations"
      kicker="Expectations"
      title="What the price assumes"
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
              At a market value of{" "}
              <span className="num font-medium">{fmtMarketCap(e.market_value)}</span>, about{" "}
              <span className="num font-medium">{e.pe?.toFixed(1)}</span> times its latest
              year's earnings, the price works out if you assume{" "}
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
                note={`A year, for ${e.years} years, if you want 12% a year from the share. ${e.implied
                  .filter((i) => i !== c)
                  .map((i) => `Asking ${i.discount_rate_pct}%: ${pct(i.growth_pct)}`)
                  .join(". ")}.`}
              />
              <Tile
                label="What the company did"
                value={pct(e.own.earnings_growth_pct)}
                note={
                  e.own.years
                    ? `Earnings a year over ${e.own.years} years (${fmtDate(e.own.from_year_end)} to ${fmtDate(e.own.to_year_end)}). Revenue: ${pct(e.own.revenue_growth_pct)} a year.`
                    : "Fewer than two full years of results are stored."
                }
              />
              <Tile
                label="How common that is"
                value={pct(e.base_rate_pct, 0)}
                note={
                  e.base_rate_pct != null
                    ? `of ${e.base_rate_windows.toLocaleString("en-IN")} ${e.base_rate_years}-year stretches across listed companies grew earnings at least this fast. Ten years is a much higher bar.`
                    : "Too few company records to say."
                }
              />
            </div>

            <details className="mt-5 text-xs leading-relaxed text-faint">
              <summary className="cursor-pointer text-muted">How this is worked out</summary>
              <p className="mt-2 max-w-3xl">
                Earnings are the{" "}
                {e.earnings_basis === "last_4_quarters" ? "last four quarters" : "latest full year"}{" "}
                (to {fmtDate(e.earnings_period_end)}). The model grows them at one steady rate for{" "}
                {e.years} years, then at {e.terminal_growth_pct.toFixed(0)}% a year for ever (about
                India's long-run growth), and discounts everything back at the return you ask for.
                The growth shown is the rate at which that adds up to today's market value. It
                treats all profit as money owners could take out; a company that must reinvest most
                of its profit to grow needs more than this. A lens on expectations, not a forecast
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
