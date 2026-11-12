import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { MarketMap } from "@/components/landing/MarketMap";

/**
 * Hero: the claim on the left, the product's answer on the right. The visual
 * is not a mock-up: it is the live market map, every ranked company plotted
 * from the same scores the screener uses.
 */
export function Hero() {
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 pb-14 pt-12 md:px-6 md:pb-20 md:pt-16">
        <div className="grid items-center gap-10 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <p className="label-caps mb-5">Equity research · India</p>
            <h1 className="font-display text-4xl font-bold leading-[1.1] tracking-[-0.015em] md:text-[52px] md:leading-[1.06]">
              The market doesn't need more noise.
              <br />
              <span className="text-cobalt dark:text-cobalt-strong">It needs better research.</span>
            </h1>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-muted">
              SignalDesk reads the same public numbers everyone else sees and turns them
              into <span className="hi">structured, explainable research</span>: fundamentals,
              relative valuation, technical positioning and news sentiment for the 1,000
              largest listed companies.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button asChild size="lg" className="gap-2">
                <Link to="/markets">
                  Explore the research
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <a href="#how-it-works">See how it works</a>
              </Button>
            </div>
            <p className="mt-8 max-w-md border-l-2 border-cobalt pl-4 text-sm leading-relaxed text-muted">
              The map is the whole universe at today's scores. Each dot is a company
              you can open.
            </p>
          </div>

          <div className="lg:col-span-7">
            <MarketMap />
          </div>
        </div>
      </div>
    </section>
  );
}
