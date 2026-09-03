// Typed mirrors of the backend's pydantic response models (backend/app/routers).
// Field names are snake_case on purpose — they match the wire format exactly.

export interface StockSummary {
  symbol: string;
  name: string;
  sector: string | null;
  last_price: number;
  change_pct: number;
}

export interface StockListResponse {
  items: StockSummary[];
  total: number;
  page: number;
  limit: number;
}

export interface QuoteBlock {
  last_price: number | null;
  change_abs: number | null;
  change_pct: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  prev_close: number | null;
  volume: number | null;
  date: string | null;
}

export interface StockDetail {
  symbol: string;
  name: string;
  sector: string | null;
  industry: string | null;
  market_cap: number | null;
  quote: QuoteBlock;
}

export interface PriceBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface PriceHistory {
  symbol: string;
  range: string;
  items: PriceBar[];
}

export interface Fundamentals {
  symbol: string;
  key_ratios: Record<string, number | null>;
  updated_at: string | null;
}

export interface ScoreComponent {
  name: string;
  value: number;
  score: number;
}

export interface ScoreCard {
  symbol: string;
  profitability: number | null;
  solvency: number | null;
  profitability_components: ScoreComponent[];
  solvency_components: ScoreComponent[];
  explanation: string;
}

export interface Valuation {
  symbol: string;
  method: string;
  metric: string;
  peers: string[];
  current: number;
  peer_median: number;
  margin_pct: number;
  status: "undervalued" | "overvalued" | "fairly_valued";
  computed_at: string;
}

export interface ValueSignal {
  metric: string | null;
  status: string | null;
  margin_pct: number | null;
  explanation: string | null;
}

export interface AlphaResponse {
  symbol: string;
  date: string;
  composite: number | null;
  fundamental: number | null;
  technical: number | null;
  sentiment: number | null;
  components: Record<string, number>;
  weights: Record<string, number>;
  value_signal: ValueSignal | null;
  explanation: string;
  insufficient_data: boolean;
}

export interface MacdBlock {
  macd: number | null;
  signal: number | null;
  histogram: number | null;
}

export interface Technicals {
  symbol: string;
  score: number | null;
  components: Record<string, number | null>;
  sma20: number | null;
  ema12: number | null;
  rsi14: number | null;
  macd: MacdBlock;
  last_close: number | null;
  closes_used: number;
  insufficient_data: boolean;
}

export interface NewsArticle {
  id: number;
  source: string;
  title: string;
  url: string;
  published_at: string | null;
  sentiment: string | null;
}

export interface NewsListResponse {
  items: NewsArticle[];
}

export interface Sentiment {
  symbol: string;
  score: number;
  label: string;
  count: number;
}

export interface ScreenResult {
  symbol: string;
  name: string;
  sector: string | null;
  industry: string | null;
  profitability: number | null;
  solvency: number | null;
  valuation_status: string | null;
  margin_pct: number | null;
}

export interface ScreenerResponse {
  items: ScreenResult[];
  total: number;
  page: number;
  limit: number;
}

export type ExplainQuestionType =
  | "alpha"
  | "technical"
  | "valuation"
  | "fundamental"
  | "sentiment";

export interface ExplainResponse {
  symbol: string;
  question_type: string;
  explanation: string;
}
