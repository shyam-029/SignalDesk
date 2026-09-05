import { CollapsibleSection } from "@/components/stock/CollapsibleSection";

/**
 * StockMethodology: compact transparency block: how each number on THIS page
 * was built, and the separation between Alpha and valuation. Collapsible
 * since Part D (static reference content; no data-backed summary).
 */
export function StockMethodology({ symbol }: { symbol: string }) {
  return (
    <CollapsibleSection
      id="methodology"
      index="08"
      kicker="Methodology"
      title="How this page is built"
      className="border-b-0"
    >
      <div className="grid gap-px border border-line bg-line md:grid-cols-2">
        {BLOCKS.map((b) => (
          <div key={b.title} className="bg-surface p-5">
            <p className="label-caps">{b.title}</p>
            <p className="mt-2 text-sm leading-relaxed text-muted">{b.body}</p>
          </div>
        ))}
      </div>
      <p className="num mt-4 text-xs text-faint">
        {symbol} · daily bars via Yahoo Finance · financials are point-in-time snapshots ·
        sentiment via FinBERT · generated explanations are built from computed data and are
        not investment advice.
      </p>
    </CollapsibleSection>
  );
}

const BLOCKS = [
  {
    title: "Alpha Score",
    body: "40% fundamental + 30% technical + 30% sentiment, renormalized over available components. Valuation is not blended in: multiples already derive from fundamentals, so blending would double-count.",
  },
  {
    title: "Fundamental scores",
    body: "Profitability: ROE 40%, ROA 20%, operating margin 20%, net margin 20%, mapped through fixed thresholds (e.g. ROE 20%+ = 100). Solvency: D/E 50%, interest coverage 30%, current ratio 20% (lower leverage scores higher). Missing metrics drop and remaining weights renormalize.",
  },
  {
    title: "Technical positioning",
    body: "Trend 50% (close vs SMA20), momentum 30% (MACD histogram), mean reversion 20% (RSI 14). The verdict describes the aggregate technical evidence only. These are explainable heuristics, not predictive models.",
  },
  {
    title: "Valuation",
    body: "Relative multiples: P/E, EV/EBITDA, P/B and P/S against the median of same-industry peers from the catalog. Outside plus or minus 5% of the median a stock reads undervalued/overvalued; within the band, fairly valued. 'Cheaper than peers' is not intrinsically cheap.",
  },
  {
    title: "Sentiment",
    body: "Recent news per stock is scored by FinBERT (positive/negative/neutral). The confidence-weighted net score (-1 to +1) maps to 0 to 100 for the Alpha blend.",
  },
  {
    title: "Data freshness",
    body: "Prices are ingested daily; financials are snapshots with an explicit updated date. Where data is missing, the page says so. Nothing is estimated or interpolated.",
  },
];
