// Collapsed-section summaries: one concise, data-backed conclusion per
// research section, shown in its header while collapsed (Part D).
//
// Rules:
//   - Every builder returns null when the data needed for a conclusion is
//     missing or insufficient. A collapsed section with no data shows no
//     summary; it never invents one.
//   - Wording follows the copy discipline: no em dashes, no AI-tell words.
//   - These are presentation strings only; every number comes straight from
//     a backend response (the frontend never recomputes financial math).

import type {
  AlphaResponse,
  NewsArticle,
  PerformanceResponse,
  ScoreCard,
  Technicals,
  Valuation,
} from "@/lib/types";
import { scoreBand, technicalVerdict, valuationSemantics } from "@/lib/semantic";

/** "Fairly valued · P/E 16.6 vs 17.3 peers" or null when not computable. */
export function valuationSummary(valuation: Valuation | undefined): string | null {
  if (!valuation) return null;
  const sem = valuationSemantics(valuation.status);
  if (!sem) return null;
  return `${sem.short} · ${valuation.metric} ${trim1(valuation.current)} vs ${trim1(
    valuation.peer_median,
  )} peers`;
}

/**
 * "Strong profitability · ROE 21.4%" (or the solvency equivalent), or a
 * neutral "Scores 64 / 81" read, or null when nothing is computable.
 */
export function fundamentalsSummary(scores: ScoreCard | undefined): string | null {
  if (!scores) return null;
  const p = scores.profitability;
  const s = scores.solvency;
  if (p == null && s == null) return null;

  const bandFor = (v: number | null) => scoreBand(v);
  const pBand = bandFor(p);
  const sBand = bandFor(s);
  const rank = (b: ReturnType<typeof scoreBand>) =>
    b ? ["veryweak", "weak", "moderate", "positive", "strong"].indexOf(b.key) : -1;

  // Headline the stronger dimension; detail it with its leading raw input.
  // Component names match the backend's metric table ("ROE", "Debt/Equity").
  if (p != null && (s == null || rank(pBand) >= rank(sBand))) {
    const roe = scores.profitability_components.find((c) => c.name === "ROE");
    const word = strengthWord(p);
    return roe
      ? `${word} profitability · ROE ${trim1(roe.value)}%`
      : `${word} profitability · score ${p}`;
  }
  if (s != null) {
    const de = scores.solvency_components.find((c) => c.name === "Debt/Equity");
    const word = strengthWord(s);
    return de
      ? `${word} solvency · D/E ${trim1(de.value)}%`
      : `${word} solvency · score ${s}`;
  }
  return null;
}

/**
 * "Bullish · RSI 62.4" style technical summary, or null when the indicator
 * set has insufficient data. The verdict describes technical positioning
 * only, never the stock itself.
 */
export function technicalsSummary(technicals: Technicals | undefined): string | null {
  if (!technicals || technicals.insufficient_data) return null;
  const verdict = technicalVerdict(technicals.score);
  if (!verdict) return null;
  if (technicals.rsi14 != null) {
    return `${verdict.word} · RSI ${technicals.rsi14.toFixed(1)}`;
  }
  return `${verdict.word} · score ${technicals.score}`;
}

/**
 * "12 articles · net sentiment Positive" or null while nothing is scored.
 */
export function newsSummary(
  articles: NewsArticle[] | undefined,
  netLabel: string | null | undefined,
): string | null {
  if (!articles || articles.length === 0) return null;
  const count = articles.length;
  if (!netLabel) return `${count} article${count === 1 ? "" : "s"} · sentiment unscored`;
  return `${count} article${count === 1 ? "" : "s"} · net sentiment ${netLabel}`;
}

/**
 * Compact performance read for the strip's fallback line, or null when the
 * windows themselves are missing (insufficient history is handled by the
 * strip's DataState instead).
 */
export function performanceSummary(perf: PerformanceResponse | undefined): string | null {
  if (!perf || perf.insufficient_data) return null;
  const oneY = perf.windows["1y"]?.change_pct;
  if (oneY == null) return null;
  return `1Y ${oneY > 0 ? "+" : ""}${oneY.toFixed(1)}%`;
}

/** Alpha snapshot headline for the research header, or null. */
export function alphaHeadline(alpha: AlphaResponse | undefined): string | null {
  if (!alpha || alpha.composite == null) return null;
  return `Alpha ${alpha.composite}/100`;
}

function strengthWord(score: number): string {
  const band = scoreBand(score);
  if (!band) return "Mixed";
  switch (band.key) {
    case "strong":
      return "Strong";
    case "positive":
      return "Solid";
    case "moderate":
      return "Mixed";
    case "weak":
      return "Weak";
    default:
      return "Fragile";
  }
}

function trim1(value: number): string {
  return Number(value.toFixed(1)).toString();
}
