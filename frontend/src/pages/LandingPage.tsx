import { Hero } from "@/components/landing/Hero";
import { Framework } from "@/components/landing/Framework";
import { ProductPreview } from "@/components/landing/ProductPreview";
import { Coverage } from "@/components/landing/Coverage";
import { MethodologyTeaser } from "@/components/landing/MethodologyTeaser";
import { FinalCTA } from "@/components/landing/FinalCTA";
import { MarketPulse } from "@/components/landing/MarketPulse";
import { TickerTape } from "@/components/landing/TickerTape";
import { CandleField } from "@/components/landing/CandleField";
import { ScrollPulse } from "@/components/landing/ScrollPulse";
import { Movers } from "@/components/landing/Movers";
import { SectorBoard } from "@/components/landing/SectorBoard";
import { LatestNews } from "@/components/landing/LatestNews";
import { ExplainerSection } from "@/components/landing/ExplainerSection";

/**
 * Landing: a long read built from stored market data. In order: the Nifty 50
 * ticker and index row; the claim beside the live market map; today's Nifty
 * 50 in one chart; the day's movers; the universe folded by sector; the
 * framework; the real research screen; how conclusions are explained; the
 * latest scored headlines; coverage; methodology. The sine scroll rail rides
 * the right edge.
 */
export default function LandingPage() {
  return (
    <div>
      <ScrollPulse />
      <TickerTape />
      <MarketPulse />
      <Hero />

      {/* Today's market in one picture: the Nifty 50, one bar per company. */}
      <section className="section-alt border-b border-line">
        <div className="mx-auto max-w-6xl px-4 py-14 md:px-6">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="label-caps mb-1.5">Today's close</p>
              <h2 className="font-display text-2xl font-semibold tracking-[-0.01em] md:text-[26px]">
                The Nifty 50, one bar per company
              </h2>
            </div>
            <p className="max-w-sm text-xs leading-relaxed text-muted">
              Largest company on the left. Bar height is the day's move; green closed up,
              red closed down.
            </p>
          </div>
          <div className="chart-frame">
            <CandleField />
          </div>
        </div>
      </section>

      <Movers />
      <SectorBoard />
      <Framework />
      <ProductPreview />
      <ExplainerSection />
      <LatestNews />
      <Coverage />
      <MethodologyTeaser />
      <FinalCTA />
    </div>
  );
}
