// Typed mirrors of the backend's pydantic response models (backend/app/routers).
// Field names are snake_case on purpose: they match the wire format exactly.

export interface StockSummary {
  symbol: string;
  name: string;
  sector: string | null;
  industry: string | null;
  // null when the stock has no stored price bars - the API never fabricates.
  last_price: number | null;
  change_pct: number | null;
  market_cap: number | null;
}

export interface StockListResponse {
  items: StockSummary[];
  total: number;
  page: number;
  limit: number;
  sectors: string[];
}

// Server-side universe search (GET /stocks/search?q=).
export interface StockSearchResponse {
  items: Array<{ symbol: string; name: string }>;
  query: string;
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
  // true when the latest bar is older than the price freshness window.
  stale: boolean | null;
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

// Altman Z-Score distress diagnostic (GET /stocks/{symbol}/altman).
// Separate from ScoreCard by design: never blended into solvency or Alpha.
export interface AltmanResponse {
  symbol: string;
  status: "available" | "unavailable";
  score: number | null;
  zone: "safe" | "grey" | "distress" | null;
  formulation: string;
  inputs_used: Record<string, number>;
  missing_inputs: string[];
  reason: string | null;
  detail: string | null;
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
  insufficient_data: boolean;
}

// Lazy companion to /alpha: the written narrative (Part I split - the score
// path never waits on the LLM).
export interface AlphaExplanationResponse {
  symbol: string;
  explanation: string;
  // Provenance of the text: LLM narrative vs deterministic rule fallback.
  source: "llm" | "rule_based";
}

// Provider-sourced company background ("About the company" box).
export interface CompanyProfileResponse {
  symbol: string;
  business_summary: string | null;
  ceo: string | null;
  employees: number | null;
  website: string | null;
  source: string | null;
  updated_at: string | null;
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
  // null when the stock has no scored articles (never a fabricated 0/neutral).
  score: number | null;
  label: string | null;
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

// Part H: grounded single-shot ask (POST /stocks/{symbol}/ask).
export type AskSource = "model" | "rule_based" | "scope" | "insufficient";
export type AskConfidence = "high" | "medium" | "low";

export interface AskResponse {
  symbol: string;
  answer: string;
  evidence: string[];
  confidence: AskConfidence;
  source: AskSource;
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
  /** Number of stored periods summed into this row (grouped views only). */
  aggregated_from?: number | null;
}

export interface FinancialsHistoryResponse {
  symbol: string;
  items: FinancialPeriodItem[];
  insufficient_data: boolean;
}

// --- ETF domain (GET /etfs, Plan 9 slice) -------------------------------------

export interface EtfSummary {
  symbol: string;
  name: string;
  last_price: number | null;
  change_pct: number | null;
  return_1y_pct: number | null;
  as_of: string | null;
}

export interface EtfListResponse {
  items: EtfSummary[];
  total: number;
}

// --- Mutual funds (GET /funds, Plan 8 slice) -----------------------------------

export interface FundSummary {
  id: number;
  amfi_code: string;
  name: string;
  category: string | null;
  plan: string | null;
  option: string | null;
  latest_nav: number | null;
  nav_date: string | null;
  return_1m_pct: number | null;
  return_3m_pct: number | null;
  return_6m_pct: number | null;
  // 1y/3y are annualised (CAGR %) by the backend.
  return_1y_pct: number | null;
  return_3y_pct: number | null;
}

export interface FundListResponse {
  items: FundSummary[];
  total: number;
}

export interface NavPoint {
  date: string;
  nav: number;
  source: string;
}

export interface FundDetailResponse {
  id: number;
  amfi_code: string;
  name: string;
  category: string | null;
  plan: string | null;
  option: string | null;
  latest_nav: number | null;
  nav_date: string | null;
  return_1m_pct: number | null;
  return_3m_pct: number | null;
  return_6m_pct: number | null;
  return_1y_pct: number | null;
  return_3y_pct: number | null;
  nav_points: number;
  history_start: string | null;
  history_end: string | null;
  items: NavPoint[];
}

// --- Market dashboard (GET /benchmarks, GET /market/news) ----------------------

export interface BenchmarkCard {
  symbol: string;
  name: string | null;
  latest_close: number | null;
  change_pct: number | null;
  as_of: string | null;
  sparkline: number[];
}

export interface BenchmarkListResponse {
  items: BenchmarkCard[];
}

export interface MarketNewsItem {
  id: number;
  symbol: string;
  title: string;
  source: string;
  url: string;
  published_at: string | null;
  sentiment: string | null;
}

export interface MarketNewsResponse {
  items: MarketNewsItem[];
}
