import * as React from "react";
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
import { ErrorBoundary } from "@/components/data/ErrorBoundary";
import { ScrollPulse } from "@/components/landing/ScrollPulse";
import { cn, normalizeSymbol } from "@/lib/utils";
import { recordRecent } from "@/lib/recent";
import { useStockDetail } from "@/lib/hooks";

/**
 * StockDetail: the deep-linkable research report for one company. Snapshot,
 * performance strip, a sticky section index, alpha (open, with its history
 * chart), the primary price chart (open), then collapsible research sections:
 * valuation (with the peer table), fundamentals (with multi-year financials),
 * technicals (with indicator series), news and methodology. Each collapsed
 * section shows a data-backed summary line. Every section sits in its own
 * error boundary: one crashed section can never blank the whole page. Each
 * visit records the stock in the device-local "recently viewed" list.
 */

const SECTIONS = [
  { id: "alpha", label: "Alpha" },
  { id: "price", label: "Price" },
  { id: "valuation", label: "Valuation" },
  { id: "fundamentals", label: "Fundamentals" },
  { id: "technicals", label: "Technicals" },
  { id: "news", label: "News" },
  { id: "methodology", label: "Methodology" },
] as const;

export default function StockDetailPage() {
  const { symbol = "" } = useParams();
  const canonical = normalizeSymbol(symbol);
  const detail = useStockDetail(canonical);

  // Recently viewed: recorded once the detail (name + day snapshot) loads.
  React.useEffect(() => {
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
      <SectionIndex />
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

/**
 * SectionIndex: a sticky row of in-page links under the site header, so a
 * long report can be navigated like a document. The current section is
 * tracked with an IntersectionObserver over the section elements; sections
 * that are not on the page (a crashed boundary) are simply skipped.
 */
function SectionIndex() {
  const [active, setActive] = React.useState<string>(SECTIONS[0].id);

  React.useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      // A band just under the sticky bars: the section crossing it is current.
      { rootMargin: "-120px 0px -65% 0px" },
    );
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  return (
    <nav
      aria-label="Report sections"
      className="sticky top-14 z-30 border-b border-line bg-background"
    >
      <div className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 md:px-6">
        {SECTIONS.map((s) => (
          <a
            key={s.id}
            href={`#${s.id}`}
            aria-current={active === s.id ? "true" : undefined}
            className={cn(
              "-mb-px shrink-0 border-b-2 px-3 py-2.5 text-xs font-medium transition-colors",
              active === s.id
                ? "border-cobalt text-foreground"
                : "border-transparent text-muted hover:text-foreground",
            )}
          >
            {s.label}
          </a>
        ))}
      </div>
    </nav>
  );
}
