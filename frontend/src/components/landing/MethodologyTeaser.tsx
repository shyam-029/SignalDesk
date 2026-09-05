import { Link } from "react-router-dom";
import { ChevronDown } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Reveal } from "@/components/motion/Reveal";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * MethodologyTeaser: transparency as a feature. "Know how the number was
 * built." Expandable rows for each analytical surface; the full page lives at
 * /methodology.
 */
const ITEMS = [
  {
    key: "Alpha Score",
    body: "40% fundamental + 30% technical + 30% sentiment, renormalized over available components, bounded 0 to 100. Valuation is left out of the blend and reported separately.",
  },
  {
    key: "Fundamentals",
    body: "Profitability (ROE 40%, ROA 20%, operating margin 20%, net margin 20%) and solvency (D/E 50%, interest coverage 30%, current ratio 20%), each mapped through fixed thresholds. Missing metrics drop out and remaining weights renormalize.",
  },
  {
    key: "Technicals",
    body: "Trend (price vs SMA20) 50%, momentum (MACD histogram) 30%, mean reversion (RSI 14) 20%. Explicitly heuristic and explainable, not validated predictive models.",
  },
  {
    key: "Sentiment",
    body: "Recent news per stock scored by FinBERT (positive/negative/neutral). The weighted net score feeds the sentiment component of Alpha.",
  },
  {
    key: "Valuation",
    body: "Relative multiples: the stock's P/E, EV/EBITDA, P/B and P/S against the median of same-industry peers. Outside plus or minus 5% of the median the stock reads undervalued/overvalued. Kept separate from Alpha by design.",
  },
];

export function MethodologyTeaser() {
  return (
    <section className="relative border-b border-line bg-surface-2/30">
      <div className="mx-auto max-w-6xl px-4 py-20 md:px-6 md:py-28">
        <div className="grid gap-12 lg:grid-cols-12">
          <Reveal className="lg:col-span-5">
            <p className="label-caps mb-3">Methodology</p>
            <h2 className="font-display text-3xl font-semibold leading-tight md:text-4xl">
              Know how the number was built.
            </h2>
            <p className="mt-4 text-muted">
              No black boxes. <span className="hi">Weights, thresholds and data sources are documented</span>, and every
              metric in the product carries its definition one click away.
            </p>
            <Button asChild variant="outline" className="mt-6">
              <Link to="/methodology">Read the full methodology</Link>
            </Button>
          </Reveal>

          <Reveal delay={0.1} className="lg:col-span-7">
            <div className="divide-y divide-line border-y border-line">
              {ITEMS.map((item) => (
                <Collapsible key={item.key}>
                  <CollapsibleTrigger className="group flex w-full items-center justify-between py-4 text-left">
                    <span className="text-sm font-medium">{item.key}</span>
                    <ChevronDown
                      className={cn(
                        "size-4 text-faint transition-transform",
                        "group-data-[state=open]:rotate-180",
                      )}
                    />
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <p className="pb-5 text-sm leading-relaxed text-muted">{item.body}</p>
                  </CollapsibleContent>
                </Collapsible>
              ))}
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
