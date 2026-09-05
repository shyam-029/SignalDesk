import { useParams } from "react-router-dom";

import { StockHeader } from "@/components/stock/StockHeader";
import { AlphaSection } from "@/components/stock/AlphaSection";
import { ValuationSection } from "@/components/stock/ValuationSection";
import { FundamentalsSection } from "@/components/stock/FundamentalsSection";
import { PriceTechnicals } from "@/components/stock/PriceTechnicals";
import { NewsSection } from "@/components/stock/NewsSection";
import { StockMethodology } from "@/components/stock/StockMethodology";
import { normalizeSymbol } from "@/lib/utils";

/**
 * StockDetail: the deep-linkable research report for one company. Snapshot,
 * alpha, valuation, fundamentals, price and technicals, news and sentiment,
 * then methodology. Reads like a document; unknown symbols land on the
 * "unknown symbol" state via DataState in each section.
 */
export default function StockDetailPage() {
  const { symbol = "" } = useParams();
  const canonical = normalizeSymbol(symbol);

  return (
    <div>
      <StockHeader symbol={canonical} />
      <AlphaSection symbol={canonical} />
      <ValuationSection symbol={canonical} />
      <FundamentalsSection symbol={canonical} />
      <PriceTechnicals symbol={canonical} />
      <NewsSection symbol={canonical} />
      <StockMethodology symbol={canonical} />
    </div>
  );
}
