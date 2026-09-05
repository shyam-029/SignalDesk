// Semantic scoring system: the single source of truth for analytical color.
//
// Bands (approved):
//   80-100 strong positive · 60-79 positive · 40-59 moderate
//   20-39 weak · 0-19 very weak
//
// RULE: semantic color is applied ONLY to analytical conclusions (Alpha,
// component scores, verdicts, valuation state, technical positioning).
// Raw financial metrics stay neutral. Never color a P/E just because it exists.
// Valuation carries its OWN state (cheaper/fair/expensive) and must not inherit
// Alpha's band color.

export type BandKey = "strong" | "positive" | "moderate" | "weak" | "veryweak";

export interface Band {
  key: BandKey;
  label: string;
  text: string; // text-{color}
  bg: string; // bg-{color}/10 surface tint (subtle)
  border: string; // border-{color}/35 (medium)
  bar: string; // bg-{color} for bars/indicators (strong)
}

const BANDS: Record<BandKey, Band> = {
  strong: {
    key: "strong",
    label: "Strong",
    text: "text-band-strong",
    bg: "bg-band-strong/10",
    border: "border-band-strong/35",
    bar: "bg-band-strong",
  },
  positive: {
    key: "positive",
    label: "Positive",
    text: "text-band-positive",
    bg: "bg-band-positive/10",
    border: "border-band-positive/35",
    bar: "bg-band-positive",
  },
  moderate: {
    key: "moderate",
    label: "Moderate",
    text: "text-band-moderate",
    bg: "bg-band-moderate/10",
    border: "border-band-moderate/35",
    bar: "bg-band-moderate",
  },
  weak: {
    key: "weak",
    label: "Weak",
    text: "text-band-weak",
    bg: "bg-band-weak/10",
    border: "border-band-weak/35",
    bar: "bg-band-weak",
  },
  veryweak: {
    key: "veryweak",
    label: "Very weak",
    text: "text-band-veryweak",
    bg: "bg-band-veryweak/10",
    border: "border-band-veryweak/35",
    bar: "bg-band-veryweak",
  },
};

export function scoreBand(score: number | null | undefined): Band | null {
  if (score == null || Number.isNaN(score)) return null;
  if (score >= 80) return BANDS.strong;
  if (score >= 60) return BANDS.positive;
  if (score >= 40) return BANDS.moderate;
  if (score >= 20) return BANDS.weak;
  return BANDS.veryweak;
}

/** All five example states, used on the landing page's Alpha demo. */
export const BAND_EXAMPLES: Array<{ score: number; band: Band }> = [
  { score: 82, band: BANDS.strong },
  { score: 59, band: BANDS.moderate },
  { score: 34, band: BANDS.weak },
];

// --- Valuation state (independent of Alpha) ---------------------------------

export type ValuationState = "undervalued" | "overvalued" | "fairly_valued";

export interface ValuationSemantics {
  headline: string; // "Cheaper than peers"
  short: string; // "Undervalued"
  band: Band;
}

export function valuationSemantics(
  status: string | null | undefined,
): ValuationSemantics | null {
  switch (status) {
    case "undervalued":
      return {
        headline: "Cheaper than peers",
        short: "Undervalued",
        band: BANDS.positive,
      };
    case "overvalued":
      return {
        headline: "More expensive than peers",
        short: "Overvalued",
        band: BANDS.weak,
      };
    case "fairly_valued":
      return {
        headline: "In line with peers",
        short: "Fairly valued",
        band: BANDS.moderate,
      };
    default:
      return null;
  }
}

// --- Technical positioning verdict -------------------------------------------
// Aggregate technical evidence only. Never a statement about the whole stock.

export interface TechnicalVerdict {
  word: string;
  band: Band;
}

export function technicalVerdict(score: number | null | undefined): TechnicalVerdict | null {
  if (score == null || Number.isNaN(score)) return null;
  if (score >= 80) return { word: "Strongly bullish", band: BANDS.strong };
  if (score >= 60) return { word: "Bullish", band: BANDS.positive };
  if (score >= 40) return { word: "Neutral", band: BANDS.moderate };
  if (score >= 20) return { word: "Bearish", band: BANDS.weak };
  return { word: "Strongly bearish", band: BANDS.veryweak };
}

// --- News sentiment -----------------------------------------------------------

export function sentimentSemantics(
  label: string | null | undefined,
): { label: string; band: Band } {
  switch (label) {
    case "positive":
      return { label: "Positive", band: BANDS.positive };
    case "negative":
      return { label: "Negative", band: BANDS.veryweak };
    default:
      return { label: "Neutral", band: BANDS.moderate };
  }
}
