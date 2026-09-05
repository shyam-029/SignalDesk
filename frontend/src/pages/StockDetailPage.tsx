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
import { normalizeSymbol } from "@/lib/utils";

/**
 * StockDetail: the deep-linkable research report for one company. Snapshot,
 * performance strip, alpha (open, with its history chart), the primary price
 * chart (open), then collapsible research sections - valuation (with the
 * peer table), fundamentals (with multi-year financials), technicals (with
 * indicator series), news and methodology - each showing a data-backed
 * summary line while collapsed. Reads like a document; unknown symbols land
 * on the "unknown symbol" state via DataState in each section.
 */
export default function StockDetailPage() {
  const { symbol = "" } = useParams();
  const canonical = normalizeSymbol(symbol);

  return (
    <div>
      <StockHeader symbol={canonical} />
      <PerformanceStrip symbol={canonical} />
      <AlphaSection symbol={canonical} />
      <PriceSection symbol={canonical} />
      <ValuationSection symbol={canonical} />
      <FundamentalsSection symbol={canonical} />
      <TechnicalsSection symbol={canonical} />
      <NewsSection symbol={canonical} />
      <StockMethodology symbol={canonical} />
    </div>
  );
}
