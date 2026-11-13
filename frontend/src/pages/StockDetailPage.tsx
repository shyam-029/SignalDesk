import * as React from "react";
import { useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { PanelRightClose, PanelRightOpen } from "lucide-react";

import { StockHeader } from "@/components/stock/StockHeader";
import { PerformanceStrip } from "@/components/stock/PerformanceStrip";
import { AlphaSection } from "@/components/stock/AlphaSection";
import { PriceSection } from "@/components/stock/PriceTechnicals";
import { ValuationSection } from "@/components/stock/ValuationSection";
import { FundamentalsSection } from "@/components/stock/FundamentalsSection";
import { TechnicalsSection } from "@/components/stock/TechnicalsSection";
import { RiskSection } from "@/components/stock/RiskSection";
import { OwnershipSection } from "@/components/stock/OwnershipSection";
import { AtAGlance } from "@/components/stock/AtAGlance";
import { NewsSection } from "@/components/stock/NewsSection";
import { StockMethodology } from "@/components/stock/StockMethodology";
import { ErrorBoundary } from "@/components/data/ErrorBoundary";
import { ScrollPulse } from "@/components/landing/ScrollPulse";
import { cn, normalizeSymbol } from "@/lib/utils";
import { recordRecent } from "@/lib/recent";
import { useStockDetail } from "@/lib/hooks";
import { loadStockSnapshot } from "@/lib/stockSnapshot";

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

/** Two sections share a row once the report column is wide enough. */
const PAIR =
  "@[1300px]:grid @[1300px]:grid-cols-2 @[1300px]:[&>section:first-child]:border-r @[1300px]:[&>section]:min-w-0";

/** Device-local memory of whether the summary rail is open. */
const RAIL_KEY = "signaldesk.stock.rail";

const SECTIONS = [
  { id: "alpha", label: "Alpha" },
  { id: "price", label: "Price" },
  { id: "valuation", label: "Valuation" },
  { id: "fundamentals", label: "Fundamentals" },
  { id: "ownership", label: "Ownership" },
  { id: "technicals", label: "Technicals" },
  { id: "risk", label: "Risk" },
  { id: "news", label: "News" },
  { id: "methodology", label: "Methodology" },
] as const;

export default function StockDetailPage() {
  const { symbol = "" } = useParams();
  const canonical = normalizeSymbol(symbol);
  const queryClient = useQueryClient();
  const detail = useStockDetail(canonical);

  // In-app navigation to another stock: seed its nightly snapshot (a no-op
  // for the symbol already fetched at app start).
  React.useEffect(() => {
    void loadStockSnapshot(queryClient, canonical);
  }, [queryClient, canonical]);

  // Recently viewed: recorded once the detail (name + day snapshot) loads.
  React.useEffect(() => {
    const d = detail.data;
    if (d) {
      recordRecent(d.symbol, d.name, d.quote.last_price, d.quote.change_pct);
    }
  }, [detail.data]);

  // Summary rail: open by default, remembered per device. Collapsed, the
  // report takes the full width and its panels sit side by side instead.
  const [railOpen, setRailOpen] = React.useState<boolean>(() => {
    try {
      return window.localStorage.getItem(RAIL_KEY) !== "closed";
    } catch {
      return true;
    }
  });
  const toggleRail = React.useCallback(() => {
    setRailOpen((open) => {
      try {
        window.localStorage.setItem(RAIL_KEY, open ? "closed" : "open");
      } catch {
        // Storage unavailable (private window): the choice lasts for this visit.
      }
      return !open;
    });
  }, []);

  return (
    <div className="stock-page">
      <ScrollPulse />
      <StockHeader symbol={canonical} />
      <ErrorBoundary label="performance">
        <PerformanceStrip symbol={canonical} />
      </ErrorBoundary>
      <SectionIndex railOpen={railOpen} onToggleRail={toggleRail} />
      {/* Wide screens: the report on the left, a sticky summary rail on the
          right. Below xl the rail is hidden and the report takes the width.
          The report column is a size container so its panels can pair up
          when it is wide (rail collapsed). */}
      <div
        className={cn(
          "mx-auto max-w-[1500px]",
          railOpen && "xl:grid xl:grid-cols-[minmax(0,1fr)_340px]",
        )}
      >
      <div className="@container min-w-0">
      {/* Wide column (rail collapsed): the score and the chart share a row,
          with the chart staying in view beside the longer Alpha column. */}
      <div className={cn(PAIR, "@[1300px]:[&>section:last-child>div]:sticky @[1300px]:[&>section:last-child>div]:top-28")}>
      <ErrorBoundary label="Alpha">
        <AlphaSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="price chart">
        <PriceSection symbol={canonical} />
      </ErrorBoundary>
      </div>
      <ErrorBoundary label="valuation">
        <ValuationSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="fundamentals">
        <FundamentalsSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="ownership">
        <OwnershipSection symbol={canonical} />
      </ErrorBoundary>
      <div className={PAIR}>
      <ErrorBoundary label="technicals">
        <TechnicalsSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="risk">
        <RiskSection symbol={canonical} />
      </ErrorBoundary>
      </div>
      <ErrorBoundary label="news">
        <NewsSection symbol={canonical} />
      </ErrorBoundary>
      <ErrorBoundary label="methodology">
        <StockMethodology symbol={canonical} />
      </ErrorBoundary>
      </div>
      {railOpen && (
        <aside aria-label="At a glance" className="hidden border-l border-line xl:block">
          <div className="sticky top-[6.5rem] max-h-[calc(100vh-6.5rem)] overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <ErrorBoundary label="summary">
              <AtAGlance symbol={canonical} onCollapse={toggleRail} />
            </ErrorBoundary>
          </div>
        </aside>
      )}
      </div>
    </div>
  );
}

/**
 * SectionIndex: a sticky row of in-page links under the site header, so a
 * long report can be navigated like a document. The current section is
 * tracked with an IntersectionObserver over the section elements; sections
 * that are not on the page (a crashed boundary) are simply skipped.
 */
function SectionIndex({
  railOpen,
  onToggleRail,
}: {
  railOpen: boolean;
  onToggleRail: () => void;
}) {
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
      {/* Sideways scroll on narrow screens only, with no visible scrollbar:
          the bar itself must never grow a vertical scroller. */}
      <div className="mx-auto flex max-w-[1500px] gap-1 overflow-x-auto overflow-y-hidden px-4 [scrollbar-width:none] md:px-6 [&::-webkit-scrollbar]:hidden">
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
        {/* Summary rail switch: only where the rail can show (xl and up). */}
        <button
          type="button"
          onClick={onToggleRail}
          aria-pressed={railOpen}
          className="ml-auto hidden shrink-0 items-center gap-1.5 px-3 py-2.5 text-xs font-medium text-muted transition-colors hover:text-foreground xl:inline-flex"
        >
          {railOpen ? (
            <PanelRightClose aria-hidden className="size-4" />
          ) : (
            <PanelRightOpen aria-hidden className="size-4" />
          )}
          {railOpen ? "Hide summary" : "Show summary"}
        </button>
      </div>
    </nav>
  );
}
