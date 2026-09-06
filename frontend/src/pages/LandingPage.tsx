import { usePrices } from "@/lib/hooks";

import { Hero } from "@/components/landing/Hero";
import { NumbersProblem } from "@/components/landing/NumbersProblem";
import { Framework } from "@/components/landing/Framework";
import { AlphaStates } from "@/components/landing/AlphaStates";
import { ExplainerSection } from "@/components/landing/ExplainerSection";
import { ProductPreview } from "@/components/landing/ProductPreview";
import { UniverseStrip } from "@/components/landing/UniverseStrip";
import { Coverage } from "@/components/landing/Coverage";
import { MethodologyTeaser } from "@/components/landing/MethodologyTeaser";
import { FinalCTA } from "@/components/landing/FinalCTA";
import { MarketPulse } from "@/components/landing/MarketPulse";
import { CandleField } from "@/components/landing/CandleField";
import { ScrollPulse } from "@/components/landing/ScrollPulse";

/**
 * Landing: an editorial sequence, not a template. Raw numbers move through
 * structure, analysis and research into one signal. Sections show their real
 * states when the API is unreachable (DataState everywhere); no mock data is
 * fabricated to look complete.
 */
export default function LandingPage() {
  // The hero sparkline reuses the SAME prices query as the product preview
  // (identical query key), so no extra network request.
  const prices = usePrices("RELIANCE", "6mo");
  const sparkline = prices.data
    ? prices.data.items.map((b) => b.close).slice(-120)
    : null;

  return (
    <div className="grid-lines">
      <ScrollPulse />
      <MarketPulse />
      <Hero sparkline={sparkline} />

      {/* Editorial plate: where the raw numbers come from. */}
      <section className="section-alt border-b border-line">
        <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
          <figure className="chart-frame">
            <CandleField className="h-auto w-full" />
            <figcaption className="flex items-baseline gap-3 border-t border-line px-4 py-2.5">
              <span className="label-caps">The raw feed</span>
              <span className="num text-xs text-muted">Illustrative · daily bars</span>
            </figcaption>
          </figure>
        </div>
      </section>

      <NumbersProblem />
      <Framework />
      <AlphaStates />
      <ExplainerSection />
      <ProductPreview />
      <UniverseStrip />
      <Coverage />
      <MethodologyTeaser />
      <FinalCTA />
    </div>
  );
}
