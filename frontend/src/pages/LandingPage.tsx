import { usePrices } from "@/lib/hooks";

import { Hero } from "@/components/landing/Hero";
import { NumbersProblem } from "@/components/landing/NumbersProblem";
import { Framework } from "@/components/landing/Framework";
import { AlphaStates } from "@/components/landing/AlphaStates";
import { Grounded } from "@/components/landing/Grounded";
import { ProductPreview } from "@/components/landing/ProductPreview";
import { UniverseStrip } from "@/components/landing/UniverseStrip";
import { Coverage } from "@/components/landing/Coverage";
import { MethodologyTeaser } from "@/components/landing/MethodologyTeaser";
import { FinalCTA } from "@/components/landing/FinalCTA";

/**
 * Landing — an editorial argument, not a template: raw numbers → structure →
 * analysis → research → signal. Sections degrade honestly when the API is
 * unreachable (DataState everywhere); no mock data is fabricated to look complete.
 */
export default function LandingPage() {
  // The hero sparkline reuses the SAME prices query as the product preview
  // (identical query key) — no extra network request.
  const prices = usePrices("RELIANCE", "6mo");
  const sparkline = prices.data
    ? prices.data.items.map((b) => b.close).slice(-120)
    : null;

  return (
    <div>
      <Hero sparkline={sparkline} />
      <NumbersProblem />
      <Framework />
      <AlphaStates />
      <Grounded />
      <ProductPreview />
      <UniverseStrip />
      <Coverage />
      <MethodologyTeaser />
      <FinalCTA />
    </div>
  );
}
