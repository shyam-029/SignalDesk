// METRIC_INFO: the information system for every non-obvious financial metric,
// ratio, score, and indicator SignalDesk displays.
//
// Each entry carries:
//   label  - display name
//   short  - tooltip definition (one or two sentences)
//   method - popover methodology: how SignalDesk computes/uses it
//   longer - optional expandable context for longer explanations
//
// InfoDot consumes this; a metric missing an entry renders without its info
// affordance, so the registry doubles as a completeness checklist.

export interface MetricInfo {
  label: string;
  short: string;
  method?: string;
  longer?: string;
}

export const METRIC_INFO = {
  // --- Scores ---
  alpha: {
    label: "Alpha Score",
    short:
      "SignalDesk's composite research signal: 40% fundamental, 30% technical, 30% sentiment, renormalized when a component is unavailable.",
    method:
      "The composite blends three separate analyses: fundamental strength (profitability and solvency scores), technical positioning (trend/momentum/reversion heuristics), and news sentiment, weighted 40/30/30 and renormalized over available components. It is a research summary, not a prediction, and it is not investment advice.",
    longer:
      "Alpha leaves valuation out on purpose. Multiples derive from the same fundamentals, so blending them would double count. Valuation is reported separately as the value signal: read both, don't merge them.",
  },
  fundamental_score: {
    label: "Fundamental Score",
    short: "Mean of the profitability and solvency scores, 0 to 100.",
    method:
      "Profitability maps ROE, ROA, operating margin and net margin through fixed thresholds; solvency maps debt/equity, interest coverage and current ratio. Missing metrics are dropped and the remaining weights renormalized, so the score reflects only the data that exists.",
  },
  technical_score: {
    label: "Technical Score",
    short: "Heuristic 0 to 100 read of price structure: trend (50%), momentum (30%), mean reversion (20%).",
    method:
      "Trend scores the close relative to its 20-day SMA; momentum scores the MACD histogram; mean reversion scores RSI 14 distance from 50. Weights are renormalized when an indicator lacks data. These are product-defined heuristics, not validated predictive models.",
  },
  sentiment_score: {
    label: "Sentiment Score",
    short: "Aggregate FinBERT news sentiment for recent articles, scaled 0 to 100.",
    method:
      "Recent news headlines are scored by FinBERT (positive/negative/neutral). The net weighted score on a -1 to +1 scale is mapped to 0 to 100 for the Alpha blend.",
  },

  // --- Valuation multiples ---
  pe: {
    label: "P/E",
    short: "Price-to-earnings: price per share relative to trailing earnings per share.",
    method:
      "SignalDesk compares the stock's trailing P/E against the median of same-industry peers from its catalog. A discount to peers can indicate relative cheapness, or a weaker earnings outlook. Relative is not the same as intrinsic.",
  },
  ev_ebitda: {
    label: "EV/EBITDA",
    short: "Enterprise value relative to EBITDA; capital-structure-neutral multiple.",
    method:
      "Compares total enterprise value (market cap + debt - cash) to operating earnings before depreciation and amortization. Because EV includes debt, the multiple is more comparable across companies with different leverage than P/E.",
  },
  pb: {
    label: "P/B",
    short: "Price relative to book value (net assets).",
    method:
      "Compared against same-industry peers. Especially relevant for capital-heavy sectors like banks; less meaningful for asset-light businesses.",
  },
  ps: {
    label: "P/S",
    short: "Price relative to trailing revenue (market cap / sales).",
    method:
      "Revenue is harder to manipulate than earnings, so P/S is useful for companies with thin or negative margins, but it says nothing about profitability by itself.",
  },
  value_signal: {
    label: "Value Signal",
    short: "The relative valuation read, kept separate from Alpha.",
    method:
      "Valuation is not blended into the Alpha composite (it would double-count fundamentals). It is reported alongside so the two conclusions can be read together.",
  },
  margin_vs_peers: {
    label: "Margin vs peer median",
    short: "How far the stock's multiple sits from its industry median. Negative = trading below peers.",
    method:
      "margin = (stock multiple / peer median - 1) x 100. Outside plus or minus 5% the stock is classified undervalued/overvalued relative to peers; inside the band it is fairly valued.",
    longer:
      "The peer set is same-industry companies from SignalDesk's stock catalog (industry fallback to sector). 'Relatively cheaper' does not mean intrinsically cheap; the whole sector may be expensive.",
  },
  ev: {
    label: "Enterprise Value",
    short: "Market cap + total debt - cash. The theoretical takeover price.",
    method: "Used as the numerator of EV/EBITDA. Shown as a secondary valuation input.",
  },
  ebitda: {
    label: "EBITDA",
    short: "Earnings before interest, taxes, depreciation and amortization.",
    method: "Used as the denominator of EV/EBITDA. Shown as a secondary valuation input.",
  },

  // --- Fundamentals ---
  profitability: {
    label: "Profitability Score",
    short: "0 to 100 read of ROE, ROA, operating margin and net margin against fixed thresholds.",
    method:
      "Piecewise-linear mapping: ROE 0% scores 0 pts, 20% or more scores 100 pts. Weights: ROE 40%, ROA 20%, operating margin 20%, net margin 20% (renormalized if a metric is missing).",
  },
  solvency: {
    label: "Solvency Score",
    short: "0 to 100 read of leverage and liquidity: debt/equity, interest coverage, current ratio.",
    method:
      "Piecewise-linear mapping: lower debt/equity scores higher; higher interest coverage and current ratio score higher. Weights: D/E 50%, coverage 30%, current ratio 20% (renormalized if missing).",
  },
  roe: {
    label: "ROE",
    short: "Return on equity: net income as a share of shareholders' equity.",
    method:
      "Scored 0% at 0 pts to 20% at 100 pts. High ROE with high leverage deserves a second look at the solvency column.",
  },
  roa: {
    label: "ROA",
    short: "Return on assets: net income relative to total assets.",
    method: "Scored 0% at 0 pts to 12% at 100 pts. Shows how efficiently the asset base generates profit.",
  },
  operating_margin: {
    label: "Operating margin",
    short: "Operating income as a share of revenue.",
    method: "Scored 0% at 0 pts to 25% at 100 pts.",
  },
  profit_margin: {
    label: "Net margin",
    short: "Net profit as a share of revenue.",
    method: "Scored 0% at 0 pts to 20% at 100 pts.",
  },
  de_ratio: {
    label: "Debt / Equity",
    short: "Total debt relative to shareholders' equity. Lower is generally safer.",
    method:
      "Scored 200% at 0 pts to 50% at 100 pts (lower is better). Negative D/E means net cash and scores at the top of the range.",
  },
  interest_coverage: {
    label: "Interest coverage",
    short: "How comfortably operating earnings cover interest payments.",
    method: "Scored 1x at 0 pts to 5x at 100 pts. Below 1x the company cannot cover interest from earnings.",
  },
  current_ratio: {
    label: "Current ratio",
    short: "Current assets relative to current liabilities: short-term liquidity.",
    method: "Scored 0.5x at 0 pts to 2x at 100 pts.",
  },
  market_cap: {
    label: "Market cap",
    short: "Share price x shares outstanding: the market's total valuation of the equity.",
  },

  // --- Performance strip (Part D) ---
  performance: {
    label: "Performance",
    short: "Price return over standard windows, computed from stored daily bars.",
    method:
      "Each window compares the latest close with the last close on or before the window start date. Windows without an old-enough bar are shown as '-': with shorter histories some windows simply do not exist yet.",
  },
  volatility: {
    label: "Volatility (1Y)",
    short: "Annualized standard deviation of daily returns over the last year, in percent.",
    method:
      "Computed by the backend from the stored daily closes: the sample standard deviation of daily simple returns scaled by the square root of 252 trading days. It measures how much the price swings, not its direction, and says nothing about future returns.",
  },
  week_52_range: {
    label: "52-week range",
    short: "Lowest and highest traded prices over the last 52 weeks.",
    method:
      "Taken from the daily high and low columns of the stored bars. A stock near the top of its range is not automatically expensive, and near the bottom is not automatically cheap.",
  },

  // --- Technical indicators ---
  sma20: {
    label: "SMA 20",
    short: "20-day simple moving average of the close.",
    method:
      "The trend sub-score compares the latest close with this average: above is a positive trend contribution, below is negative.",
  },
  ema12: {
    label: "EMA 12",
    short: "12-day exponential moving average, faster-reacting than the SMA.",
    method:
      "Displayed for reference; the current scoring uses SMA20 for trend. Reacts more quickly to recent prices.",
  },
  rsi14: {
    label: "RSI 14",
    short: "14-day Relative Strength Index (0 to 100).",
    method:
      "Above 70 often reads overbought, below 30 oversold. SignalDesk's mean-reversion sub-score rewards distance below 50 modestly: it is a heuristic, not a timing signal.",
  },
  macd: {
    label: "MACD",
    short: "MACD line (EMA12 - EMA26) minus its 9-day signal line.",
    method:
      "A positive, rising histogram indicates positive momentum; negative indicates the opposite. The momentum sub-score scales the histogram relative to price.",
  },
  trend: {
    label: "Trend",
    short: "Price vs SMA20 sub-score (50% of the technical score).",
  },
  momentum: {
    label: "Momentum",
    short: "MACD histogram sub-score (30% of the technical score).",
  },
  reversion: {
    label: "Mean reversion",
    short: "RSI 14 sub-score (20% of the technical score).",
  },

  // --- Data provenance ---
  net_sentiment: {
    label: "Net sentiment",
    short: "Mean FinBERT score across the stock's recent news: -1 (all negative) to +1 (all positive).",
    method:
      "Each article is scored positive/negative/neutral with a confidence. The net score weights positives +1 and negatives -1, averaged over scored articles. Feeds the sentiment component of Alpha.",
  },
  data_freshness: {
    label: "Data freshness",
    short: "Date of the latest stored daily bar or financial snapshot.",
    method:
      "Prices are ingested daily from Yahoo Finance; financials are point-in-time snapshots. SignalDesk shows the as-of date rather than claiming data is live.",
  },
} satisfies Record<string, MetricInfo>;

export type MetricKey = keyof typeof METRIC_INFO;
