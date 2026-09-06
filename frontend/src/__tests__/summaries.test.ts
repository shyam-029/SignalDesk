import { describe, expect, it } from "vitest";

import {
  alphaHeadline,
  fundamentalsSummary,
  newsSummary,
  performanceSummary,
  technicalsSummary,
  valuationSummary,
} from "@/lib/summaries";
import type {
  AlphaResponse,
  NewsArticle,
  PerformanceResponse,
  ScoreCard,
  Technicals,
  Valuation,
} from "@/lib/types";

const valuation = (over: Partial<Valuation> = {}): Valuation => ({
  symbol: "TCS.NS",
  method: "relative",
  metric: "P/E",
  peers: ["INFY.NS"],
  current: 16.56,
  peer_median: 17.31,
  margin_pct: -4.3,
  status: "fairly_valued",
  computed_at: "2026-09-05T00:00:00Z",
  ...over,
});

describe("valuationSummary", () => {
  it("renders status and the selected multiple vs peers", () => {
    expect(valuationSummary(valuation())).toBe("Fairly valued · P/E 16.6 vs 17.3 peers");
  });

  it("renders undervalued and overvalued states", () => {
    expect(valuationSummary(valuation({ status: "undervalued", margin_pct: -15 }))).toBe(
      "Undervalued · P/E 16.6 vs 17.3 peers",
    );
    expect(valuationSummary(valuation({ status: "overvalued", margin_pct: 22 }))).toBe(
      "Overvalued · P/E 16.6 vs 17.3 peers",
    );
  });

  it("returns null when no valuation data exists", () => {
    expect(valuationSummary(undefined)).toBeNull();
  });
});

const scoreCard = (over: Partial<ScoreCard> = {}): ScoreCard => ({
  symbol: "TCS.NS",
  profitability: 97,
  solvency: 100,
  profitability_components: [{ name: "ROE", value: 47.7, score: 100 }],
  solvency_components: [{ name: "Debt/Equity", value: 10.2, score: 100 }],
  explanation: "",
  ...over,
});

describe("fundamentalsSummary", () => {
  it("headlines the stronger dimension with its raw metric", () => {
    expect(fundamentalsSummary(scoreCard())).toBe("Strong profitability · ROE 47.7%");
  });

  it("uses solvency when it ranks higher", () => {
    const card = scoreCard({
      profitability: 40,
      solvency: 92,
      solvency_components: [{ name: "Debt/Equity", value: 36.7, score: 88 }],
    });
    expect(fundamentalsSummary(card)).toBe("Strong solvency · D/E 36.7%");
  });

  it("downgrades the word with the band", () => {
    const card = scoreCard({
      profitability: 30,
      solvency: null,
      profitability_components: [{ name: "ROE", value: 4.1, score: 20 }],
      solvency_components: [],
    });
    expect(fundamentalsSummary(card)).toBe("Weak profitability · ROE 4.1%");
  });

  it("returns null when both scores are missing", () => {
    expect(
      fundamentalsSummary(scoreCard({ profitability: null, solvency: null })),
    ).toBeNull();
    expect(fundamentalsSummary(undefined)).toBeNull();
  });
});

const technicals = (over: Partial<Technicals> = {}): Technicals => ({
  symbol: "TCS.NS",
  score: 61,
  components: { trend: 66, momentum: 55, reversion: 60 },
  sma20: 2250,
  ema12: 2260,
  rsi14: 62.4,
  macd: { macd: 1.2, signal: 1.0, histogram: 0.2 },
  last_close: 2304,
  closes_used: 200,
  insufficient_data: false,
  ...over,
});

describe("technicalsSummary", () => {
  it("joins the verdict with RSI", () => {
    expect(technicalsSummary(technicals())).toBe("Bullish · RSI 62.4");
  });

  it("falls back to the score without RSI", () => {
    expect(technicalsSummary(technicals({ rsi14: null }))).toBe("Bullish · score 61");
  });

  it("returns null when indicators have insufficient data", () => {
    expect(technicalsSummary(technicals({ insufficient_data: true }))).toBeNull();
    expect(technicalsSummary(undefined)).toBeNull();
  });
});

const article = (over: Partial<NewsArticle> = {}): NewsArticle => ({
  id: 1,
  source: "Test",
  title: "Headline",
  url: "https://example.com",
  published_at: null,
  sentiment: null,
  ...over,
});

describe("newsSummary", () => {
  it("counts articles with the net label", () => {
    expect(newsSummary([article(), article()], "Positive")).toBe(
      "2 articles · net sentiment Positive",
    );
    expect(newsSummary([article()], "Negative")).toBe(
      "1 article · net sentiment Negative",
    );
  });

  it("returns null with no articles", () => {
    expect(newsSummary([], "Positive")).toBeNull();
    expect(newsSummary(undefined, "Positive")).toBeNull();
  });
});

const performance = (over: Partial<PerformanceResponse> = {}): PerformanceResponse => ({
  symbol: "TCS.NS",
  as_of: "2026-09-04",
  bars_used: 500,
  windows: {
    "1y": {
      change_pct: 12.4,
      change_abs: 254.2,
      start_close: 2049.8,
      end_close: 2304,
      start_date: "2025-09-01",
    },
  },
  high_52w: 2400,
  low_52w: 1800,
  volatility_1y_pct: 18.2,
  insufficient_data: false,
  ...over,
});

describe("performanceSummary", () => {
  it("formats the 1Y window", () => {
    expect(performanceSummary(performance())).toBe("1Y +12.4%");
    expect(performanceSummary(performance({
      windows: { "1y": { change_pct: -3.2, change_abs: -1, start_close: 1, end_close: 1, start_date: null } },
    }))).toBe("1Y -3.2%");
  });

  it("returns null when 1Y history is missing", () => {
    expect(performanceSummary(performance({ windows: {} }))).toBeNull();
    expect(performanceSummary(performance({ insufficient_data: true }))).toBeNull();
  });
});

describe("alphaHeadline", () => {
  it("formats the composite", () => {
    const alpha = { composite: 59 } as AlphaResponse;
    expect(alphaHeadline(alpha)).toBe("Alpha 59/100");
  });

  it("returns null without a composite", () => {
    expect(alphaHeadline({ composite: null } as AlphaResponse)).toBeNull();
    expect(alphaHeadline(undefined)).toBeNull();
  });
});
