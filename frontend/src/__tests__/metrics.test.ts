import { describe, expect, it } from "vitest";

import { METRIC_INFO } from "@/lib/metrics";

/**
 * The METRIC_INFO registry doubles as a completeness checklist: every entry
 * must carry a label and a short definition. The stock page renders InfoDot
 * for each of these keys.
 */
const REQUIRED_KEYS = [
  "alpha",
  "fundamental_score",
  "technical_score",
  "sentiment_score",
  "pe",
  "ev_ebitda",
  "pb",
  "ps",
  "value_signal",
  "margin_vs_peers",
  "profitability",
  "solvency",
  "roe",
  "roa",
  "operating_margin",
  "profit_margin",
  "de_ratio",
  "interest_coverage",
  "current_ratio",
  "sma20",
  "ema12",
  "rsi14",
  "macd",
  "trend",
  "momentum",
  "reversion",
  "net_sentiment",
  "market_cap",
  "performance",
  "volatility",
  "week_52_range",
  "ev",
  "ebitda",
  "data_freshness",
] as const;

describe("METRIC_INFO registry", () => {
  it("covers every non-obvious metric the research page shows", () => {
    for (const key of REQUIRED_KEYS) {
      expect(METRIC_INFO[key], `missing METRIC_INFO[${key}]`).toBeDefined();
    }
  });

  it("gives every entry a label and a short definition", () => {
    for (const [key, info] of Object.entries(METRIC_INFO)) {
      expect(info.label, key).toBeTruthy();
      expect(info.short.length, key).toBeGreaterThan(10);
    }
  });

  it("documents valuation is separate from Alpha", () => {
    expect(METRIC_INFO.alpha.longer).toContain("valuation");
    expect(METRIC_INFO.value_signal.short).toContain("separate");
  });

  it("marks technical heuristics as non-predictive", () => {
    expect(METRIC_INFO.technical_score.method).toContain("not validated predictive models");
  });
});

