
import { SectionHeader } from "@/components/data/SectionHeader";
import { InfoDot } from "@/components/data/InfoDot";

/**
 * Methodology: the full transparency page. Documented weights, thresholds and
 * data sources; explicitly marks what is heuristic and what is relative.
 */
export default function MethodologyPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <SectionHeader index="Â§" kicker="Transparency" title="Methodology" />

      <div className="max-w-3xl space-y-12">
        <Intro />
        <Alpha />
        <Fundamental />
        <Technical />
        <Sentiment />
        <Valuation />
        <Data />
      </div>
    </div>
  );
}

function Intro() {
  return (
    <section>
      <p className="text-sm leading-relaxed text-muted">
        Every analytical output in SignalDesk is built from documented, deterministic rules
        over stored market data. Explanations are narrated by a language model that is only
        ever shown the computed facts. This page records how each number is produced.
      </p>
    </section>
  );
}

function Alpha() {
  return (
    <section>
      <h2 className="flex items-center gap-2 font-display text-2xl font-semibold">
        Alpha Score <InfoDot metric="alpha" />
      </h2>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        The composite blends three independent analyses, each scored 0 to 100: fundamental
        strength (40%), technical positioning (30%), and news sentiment (30%). Weights
        renormalize over the components that have data, so a stock without news is scored on
        the other two dimensions rather than penalized. The score is bounded 0 to 100 and is a
        research summary, not a prediction or a recommendation.
      </p>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        Valuation is left out of the blend: multiples derive from the same
        fundamentals, so blending them would double-count. It is reported separately as the
        value signal.
      </p>
    </section>
  );
}

function Fundamental() {
  return (
    <section>
      <h2 className="font-display text-2xl font-semibold">Fundamental scores</h2>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        Fixed-threshold piecewise-linear mapping (no peer-relative normalization):
        <span className="num mt-2 block border border-line bg-surface px-3 py-2 text-xs">
          score = 100 x clamp((value - floor) / (ceiling - floor), 0, 1)
        </span>
      </p>
      <table className="num mt-4 w-full border border-line text-xs">
        <thead>
          <tr className="border-b border-line bg-surface text-left">
            <th className="px-3 py-2 font-medium">Metric</th>
            <th className="px-3 py-2 font-medium">Direction</th>
            <th className="px-3 py-2 font-medium">Floor (0 pts)</th>
            <th className="px-3 py-2 font-medium">Ceiling (100 pts)</th>
            <th className="px-3 py-2 font-medium">Weight</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r[0]} className="border-b border-line last:border-b-0">
              {r.map((cell, i) => (
                <td key={i} className="px-3 py-1.5">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        Missing values drop the component and renormalize the remaining weights; if every
        component is missing the score is reported as unavailable. Negative ROE/margins clamp
        to 0; negative debt/equity (net cash) clamps to 100.
      </p>
    </section>
  );
}

function Technical() {
  return (
    <section>
      <h2 className="font-display text-2xl font-semibold">Technical positioning</h2>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        Standard parameters: SMA 20, EMA 12, RSI 14 (Wilder), MACD 12/26/9. The score weights
        trend 50% (close vs SMA20), momentum 30% (MACD histogram), and mean reversion 20%
        (RSI 14), renormalized when an indicator lacks data.
      </p>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        These are product-defined heuristics, kept simple and explainable on purpose. They are
        not validated predictive models. The verdict wording (&ldquo;Bullish&rdquo;,
        &ldquo;Bearish&rdquo; and similar) describes the aggregate technical evidence only;
        SignalDesk never labels an entire stock as bullish or bearish.
      </p>
    </section>
  );
}

function Sentiment() {
  return (
    <section>
      <h2 className="font-display text-2xl font-semibold">News sentiment</h2>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        Recent headlines per stock are scored by FinBERT (ProsusAI/finbert) into
        positive/negative/neutral with a confidence. The aggregate net score weights positives
        +1 and negatives -1, averaged over scored articles to a -1 to +1 scale, then mapped to
        0 to 100 for the Alpha blend.
      </p>
    </section>
  );
}

function Valuation() {
  return (
    <section>
      <h2 className="font-display text-2xl font-semibold">Relative valuation</h2>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        A stock's trailing multiples (P/E, EV/EBITDA, P/B, P/S) are compared with the median
        of same-industry peers drawn from the catalog (industry, with sector fallback). Margin
        = (stock / peer median - 1). Outside plus or minus 5% the stock reads undervalued or
        overvalued relative to peers; within the band, fairly valued. An empty peer set
        produces no valuation at all rather than a misleading &ldquo;fairly valued&rdquo;.
      </p>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        Relative cheapness is not intrinsic cheapness; the entire peer group can be
        expensive. Valuation is reported separately from the Alpha Score by design.
      </p>
    </section>
  );
}

function Data() {
  return (
    <section>
      <h2 className="font-display text-2xl font-semibold">Data & freshness</h2>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        Prices: daily OHLCV via Yahoo Finance for the Nifty 250 catalog (built to scale toward
        Nifty 500 as catalog rows, not code). Financials: point-in-time snapshots from the
        same provider, with an explicit updated date shown in the product. Sentiment: local
        FinBERT inference. Explanations: narration over explicitly allow-listed
        computed facts, with a rule-based fallback. Nothing is invented.
      </p>
      <p className="mt-3 text-sm leading-relaxed text-muted">
        Where data is missing or insufficient, the product shows exactly that. Nothing is
        estimated, interpolated, or fabricated to make a screen look complete. All analysis is
        informational only and is not investment advice.
      </p>
    </section>
  );
}

const ROWS: string[][] = [
  ["ROE", "higher", "0%", "20%", "40% of profitability"],
  ["ROA", "higher", "0%", "12%", "20% of profitability"],
  ["Operating margin", "higher", "0%", "25%", "20% of profitability"],
  ["Net margin", "higher", "0%", "20%", "20% of profitability"],
  ["Debt/Equity", "lower", "200%", "50%", "50% of solvency"],
  ["Interest coverage", "higher", "1Ã—", "5Ã—", "30% of solvency"],
  ["Current ratio", "higher", "0.5Ã—", "2Ã—", "20% of solvency"],
];


