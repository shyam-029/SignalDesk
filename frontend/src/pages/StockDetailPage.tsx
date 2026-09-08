import { useEffect } from "react";
import { useParams } from "react-router-dom";

import { StockHeader } from "@/components/stock/StockHeader";
import { PerformanceStrip } from "@/components/stock/PerformanceStrip";
import { AlphaSection } from "@/components/stock/AlphaSection";
import { PriceSection } from "@/components/stock/PriceTechnicals";
import { ValuationSection } from "@/components/stock/ValuationSection";
import { FundamentalsSection } from "@/components/stock/FundamentalsSection";
import { TechnicalsSection } from "@/components/stock/TechnicalsSection";
import { NewsSection } from "@/components/stock/NewsSection";
import { StockMethodology } from "@/components/stock/StockMethodology";
import { ScrollPulse } from "@/components/landing/ScrollPulse";
import { ErrorBoundary } from "@/components/data/ErrorBoundary";
import { normalizeSymbol } from "@/lib/utils";
import { recordRecent } from "@/lib/recent";
import { useStockDetail } from "@/lib/hooks";

/**
 * StockDetail: the deep-linkable research report for one company. Snapshot,
 * performance strip, alpha (open, with its history chart), the primary price
 * chart (open), then collapsible research sections - valuation (with the
 * peer table), fundamentals (with multi-year financials), technicals (with
 * indicator series), news and methodology - each showing a data-backed
 * summary line while collapsed. Every section sits in its own error
 * boundary: one crashed section can never blank the whole page. Each visit
 * records the stock in the device-local "recently viewed" list.
 */
export default function StockDetailPage() {
  const { symbol = "" } = useParams();
  const canonical = normalizeSymbol(symbol);
  const detail = useStockDetail(canonical);

  // Recently viewed: recorded once the detail (name + day snapshot) loads.
  useEffect(() => {
    const d = detail.data;
    if (d) {
      recordRecent(d.symbol, d.name, d.quote.last_price, d.quote.change_pct);
    }
  }, [detail.data]);

  return (
    <div>
      <ScrollPulse />
      <StockHeader symbol={canonical} />
      <ErrorBoundary label="performance">
        <PerformanceStrip symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="Alpha">
        <AlphaSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="price chart">
        <PriceSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="valuation">
        <ValuationSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="fundamentals">
        <FundamentalsSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="technicals">
        <TechnicalsSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="news">
        <NewsSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="methodology">
        <StockMethodology symbol={canonical} />
      </ErrorBoundary>
    </div>
  );
}
