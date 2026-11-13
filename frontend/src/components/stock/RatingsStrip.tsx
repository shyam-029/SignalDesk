import {
  useAlpha,
  useRisk,
  useScores,
  useStrength,
  useValuationHistory,
} from "@/lib/hooks";
import type { StrengthResponse } from "@/lib/types";
import { scoreBand, valuationSemantics, type Band } from "@/lib/semantic";
import { InfoDot } from "@/components/data/InfoDot";
import { cn } from "@/lib/utils";

/**
 * RatingsStrip: four separate ratings under the stock header, each answering
 * one plain question. They are shown side by side instead of being blended
 * into one number, so a good business at a high price and a poor business at
 * a low price do not look the same.
 *
 *   Quality    is this a good business?            (fundamental score)
 *   Valuation  is the price cheap or expensive?    (peers and own history)
 *   Strength   has the price been strong this year? (nightly rank)
 *   Risk       how rough is the ride?              (steadiness rank)
 *
 * Every figure comes from an endpoint the page already reads, plus
 * /strength. A rating with no data shows "-" and the reason. None of the
 * four is a forecast, and the copy never says so.
 */
export function RatingsStrip({ symbol }: { symbol: string }) {
  const alpha = useAlpha(symbol).data;
  const scores = useScores(symbol).data;
  const history = useValuationHistory(symbol).data;
  const risk = useRisk(symbol).data;
  const strength = useStrength(symbol).data;

  const signal = alpha?.value_signal ?? null;
  const peers = valuationSemantics(signal?.status);
  const ownPe = history?.multiples.find((m) => m.metric === "pe" && m.status === "available");

  return (
    <section id="ratings" aria-label="Ratings" className="border-b border-line">
      <div className="mx-auto grid max-w-[1500px] grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Card
          href="#fundamentals"
          title="Quality"
          help="Is this a good business? Built from profitability, solvency and a balance-sheet stress check. It describes the company today."
          score={alpha?.fundamental ?? null}
          word={scoreBand(alpha?.fundamental)?.label ?? null}
          band={scoreBand(alpha?.fundamental)}
          lines={[
            scores?.profitability != null ? `Profitability ${scores.profitability}` : null,
            scores?.solvency != null ? `Solvency ${scores.solvency}` : null,
          ]}
          empty="No financial statements stored yet."
        />
        <Card
          href="#valuation"
          title="Valuation"
          help="Is the price cheap or expensive? Compared with similar companies and with this company's own past. Below zero means cheaper than the median."
          word={peers?.headline ?? (ownPe ? ownVerdict(ownPe.verdict) : null)}
          band={peers?.band ?? null}
          lines={[
            signal?.margin_pct != null && signal.metric
              ? `${signal.metric} ${signed(signal.margin_pct, 0)} against peers`
              : null,
            ownPe?.vs_median_pct != null
              ? `P/E ${signed(ownPe.vs_median_pct, 0)} against its own median`
              : null,
          ]}
          empty="Not enough data to compare the price."
        />
        <Card
          href="#price"
          title="Strength"
          help="How strong has the share price been over the past year, compared with the other shares on the list? 100 is the strongest. It uses the return over the past year, leaving out the latest month, and how close the price is to its one-year high. It is not a forecast: in about one month in three, strong shares do worse than average."
          score={strength?.status === "available" ? strength.strength : null}
          word={
            strength?.status === "available" ? (scoreBand(strength.strength)?.label ?? null) : null
          }
          band={strength?.status === "available" ? scoreBand(strength.strength) : null}
          lines={
            strength?.status === "available"
              ? [
                  strength.year_return_pct != null
                    ? `${signed(strength.year_return_pct, 1)} in the year to a month ago`
                    : null,
                  strength.from_high_pct != null
                    ? strength.from_high_pct >= -0.05
                      ? "At its one-year high"
                      : `${Math.abs(strength.from_high_pct).toFixed(1)}% below its one-year high`
                    : null,
                ]
              : []
          }
          empty={strengthReason(strength)}
        />
        <Card
          href="#risk"
          title="Risk"
          help="How rough is the ride? Steadiness ranks the size of the share's price swings over the past year against the other shares on the list. 100 is the calmest."
          score={strength?.status === "available" ? strength.steadiness : null}
          word={
            strength?.status === "available" ? steadinessWord(strength.steadiness) : null
          }
          band={strength?.status === "available" ? scoreBand(strength.steadiness) : null}
          lines={[
            risk?.volatility_pct != null
              ? `Swings ${risk.volatility_pct.toFixed(0)}% a year`
              : null,
            risk?.max_drawdown.pct != null
              ? `Deepest fall ${risk.max_drawdown.pct.toFixed(0)}%`
              : null,
          ]}
          empty="Not enough price history."
        />
      </div>
    </section>
  );
}

function signed(value: number, places: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(places)}%`;
}

function ownVerdict(verdict: "below" | "near" | "above" | null): string | null {
  if (verdict === "below") return "Cheaper than its own past";
  if (verdict === "above") return "Dearer than its own past";
  if (verdict === "near") return "In line with its own past";
  return null;
}

function steadinessWord(value: number | null): string | null {
  if (value == null) return null;
  if (value >= 80) return "Very steady";
  if (value >= 60) return "Steady";
  if (value >= 40) return "Average";
  if (value >= 20) return "Jumpy";
  return "Very jumpy";
}

function strengthReason(strength: StrengthResponse | undefined): string {
  switch (strength?.status) {
    case "short_history":
      return `Needs about 13 months of prices (${strength.bars} of ${strength.bars_needed} days stored).`;
    case "suspect_move":
      return "Not rated: the stored prices show a one-day jump too big to be real, likely an unadjusted split.";
    case "stale":
      return "Not rated: the latest stored price is out of date.";
    case "not_computed":
      return "Not rated yet. Ratings are worked out each night.";
    default:
      return "-";
  }
}

function Card({
  href,
  title,
  help,
  score,
  word,
  band,
  lines,
  empty,
}: {
  href: string;
  title: string;
  help: string;
  /** 0 to 100 when the rating is a score; omitted for a verdict in words. */
  score?: number | null;
  word: string | null;
  band: Band | null;
  lines: Array<string | null>;
  empty: string;
}) {
  const shown = lines.filter((l): l is string => Boolean(l));
  const hasValue = score != null || word != null;
  return (
    <div className="border-line px-4 py-4 sm:[&:nth-child(even)]:border-l md:px-6 lg:[&:not(:first-child)]:border-l max-lg:[&:nth-child(n+3)]:border-t max-sm:[&:not(:first-child)]:border-t">
      <p className="label-caps flex items-center gap-1.5">
        <a href={href} className="underline-offset-4 hover:underline">
          {title}
        </a>
        <InfoDot info={{ label: title, short: help }} glyph="?" className="size-3.5" />
      </p>
      <div className="mt-2 flex items-baseline gap-2">
        {score != null && (
          <span className={cn("num text-2xl font-semibold", band?.text)}>{Math.round(score)}</span>
        )}
        <span
          className={cn(
            score != null ? "text-sm font-medium" : "text-base font-semibold",
            hasValue ? band?.text : "text-faint",
          )}
        >
          {hasValue ? word : "-"}
        </span>
      </div>
      {score != null && (
        <div className="mt-2 h-1 w-full bg-line">
          <div
            className={cn("h-full", band?.bar ?? "bg-faint")}
            style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
          />
        </div>
      )}
      <div className="mt-2 space-y-0.5 text-xs text-muted">
        {shown.length > 0 ? (
          shown.map((line) => (
            <p key={line} className="num">
              {line}
            </p>
          ))
        ) : hasValue ? null : (
          <p className="text-faint">{empty}</p>
        )}
      </div>
    </div>
  );
}
