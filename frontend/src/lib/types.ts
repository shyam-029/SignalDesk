// Typed mirrors of the backend's pydantic response models (backend/app/routers).
// Field names are snake_case on purpose: they match the wire format exactly.

export interface StockSummary {
  symbol: string;
  name: string;
  sector: string | null;
  industry: string | null;
  last_price: number;
  change_pct: number;
  market_cap: number | null;
}

export interface StockListResponse {
  items: StockSummary[];
  total: number;
  page: number;
  limit: number;
  sectors: string[];
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
  freshness_days?: number;
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

// --- Historical research (Phase 6.5 Part E endpoints) ------------------------

export interface WindowPerformance {
  change_pct: number | null;
  change_abs: number | null;
  start_close: number | null;
  end_close: number | null;
  start_date: string | null;
}

export interface PerformanceResponse {
  symbol: string;
  as_of: string | null;
  bars_used: number;
  windows: Record<string, WindowPerformance>;
  high_52w: number | null;
  low_52w: number | null;
  volatility_1y_pct: number | null;
  insufficient_data: boolean;
}

export interface AlphaHistoryItem {
  date: string;
  composite: number | null;
  fundamental: number | null;
  technical: number | null;
  sentiment: number | null;
  components: Record<string, number> | null;
}

export interface AlphaHistoryResponse {
  symbol: string;
  items: AlphaHistoryItem[];
  insufficient_data: boolean;
}

export interface TechnicalsSeriesItem {
  date: string;
  close: number;
  sma20: number | null;
  ema12: number | null;
  rsi14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
}

export interface TechnicalsSeriesResponse {
  symbol: string;
  items: TechnicalsSeriesItem[];
  insufficient_data: boolean;
}

export interface PeerSummary {
  symbol: string;
  name: string;
  sector: string | null;
  industry: string | null;
  last_price: number | null;
  change_pct: number | null;
  trailing_pe: number | null;
  return_on_equity: number | null;
  profit_margin: number | null;
  debt_to_equity: number | null;
}

export interface PeersResponse {
  symbol: string;
  classifier: string | null;
  count: number;
  items: PeerSummary[];
}

export interface FinancialPeriodItem {
  period_end: string;
  period_type: string;
  revenue: number | null;
  net_income: number | null;
  operating_margin: number | null;
  net_margin: number | null;
  eps: number | null;
  source: string;
  ingested_at: string;
}

export interface FinancialsHistoryResponse {
  symbol: string;
  items: FinancialPeriodItem[];
  insufficient_data: boolean;
}
