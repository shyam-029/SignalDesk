import { CheckCircle2 } from "lucide-react";

import { Reveal } from "@/components/motion/Reveal";
import { CandleField } from "@/components/landing/CandleField";

/**
 * Coverage: the product scope, stated plainly. Equities are live today; ETFs
 * and mutual funds are the planned expansion (they are core product vision in
 * the roadmap, not fake capabilities). Three different treatments, not three
 * identical cards.
 */
export function Coverage() {
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 md:px-6 md:py-28">
        <Reveal>
          <p className="label-caps mb-3">Coverage</p>
          <h2 className="max-w-2xl font-display text-3xl font-semibold leading-tight md:text-4xl">
            Built for equities. Designed for the rest of the portfolio.
          </h2>
          <p className="mt-4 max-w-xl text-muted">
            The research framework is <span className="hi">asset-class specific</span>, so each surface gets its own
            methodology, not a recycled stock page.
          </p>
        </Reveal>

        <div className="mt-12 grid gap-8 lg:grid-cols-12">
          {/* Equities: shipping today. */}
          <Reveal className="lg:col-span-5">
            <div className="relative h-full border border-cobalt/25 bg-surface p-6 pt-7">
              <span
                aria-hidden
                className="absolute left-0 top-0 h-[3px] w-full"
                style={{ background: "var(--cobalt)" }}
              />
              <div className="flex items-center justify-between">
                <p className="label-caps" style={{ color: "var(--cobalt)" }}>
                  Equities
                </p>
                <span className="inline-flex items-center gap-1 text-xs font-medium text-band-positive">
                  <CheckCircle2 className="size-3.5" /> Shipping now
                </span>
              </div>
              <h3 className="mt-3 font-display text-xl font-semibold">
                Top-1000 fundamentals, valuation, technicals, sentiment
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-muted">
                Full research screen per company: scores with per-component evidence, relative
                multiples vs industry peers, indicator-based technical positioning, FinBERT
                news sentiment, and written explanations.
              </p>
              <ul className="num mt-5 space-y-1.5 text-xs text-muted">
                {["Top-1000 ranked catalog", "Relative valuation · P/E, EV/EBITDA, P/B, P/S", "Alpha Score with the balance sheet in the blend", "ETFs and curated funds live"].map(
                  (t) => (
                    <li key={t} className="flex items-start gap-2">
                      <span className="mt-1.5 inline-block size-1 shrink-0 bg-band-strong" />
                      {t}
                    </li>
                  ),
                )}
              </ul>
            </div>
          </Reveal>

          {/* ETFs + Mutual Funds: planned, clearly marked. */}
          <div className="grid gap-8 lg:col-span-7">
            <Reveal delay={0.08} className="lg:col-span-12">
              <div className="relative flex flex-col border border-dashed border-line p-6 pt-7 md:flex-row md:items-start md:justify-between md:gap-8">
                <span
                  aria-hidden
                  className="absolute left-0 top-0 h-[3px] w-full"
                  style={{ background: "var(--accent-amber)" }}
                />
                  <div className="max-w-md">
                    <div className="flex items-center justify-between">
                      <p className="label-caps" style={{ color: "var(--accent-amber)" }}>
                        Mutual funds
                      </p>
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-band-positive">
                        <CheckCircle2 className="size-3.5" /> Shipping now
                      </span>
                    </div>
                    <h3 className="mt-3 font-display text-xl font-semibold">
                      Fund research is a different instrument.
                    </h3>
                    <p className="mt-3 text-sm leading-relaxed text-muted">
                      A curated catalog priced from the official AMFI daily NAV
                      file, with windowed returns. Fund-house holdings and
                      portfolio overlap arrive with the next data drop.
                    </p>
                  </div>
                <div className="num mt-6 shrink-0 space-y-1 text-xs text-faint md:mt-0">
                  <p>mf_nav_history · AMFI daily</p>
                  <p>mf_holdings · overlap analysis</p>
                  <p>portfolio-level Alpha view</p>
                </div>
              </div>
            </Reveal>
            <Reveal delay={0.16} className="lg:col-span-12">
              <div className="relative flex flex-col border border-dashed border-line p-6 pt-7 md:flex-row md:items-center md:justify-between md:gap-8">
                <span
                  aria-hidden
                  className="absolute left-0 top-0 h-[3px] w-full"
                  style={{ background: "var(--accent-teal)" }}
                />
                  <div className="max-w-xl">
                    <div className="flex items-center justify-between">
                      <p className="label-caps" style={{ color: "var(--accent-teal)" }}>
                        ETFs
                      </p>
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-band-positive">
                        <CheckCircle2 className="size-3.5" /> Shipping now
                      </span>
                    </div>
                    <h3 className="mt-3 font-display text-xl font-semibold">
                      Same price engine, different questions.
                    </h3>
                    <p className="mt-3 text-sm leading-relaxed text-muted">
                      The 16 largest exchange-traded funds, priced from the same
                      daily pipeline, tracked in their own domain. Tracking
                      difference and index analytics land with the ETF layer.
                    </p>
                  </div>
              </div>
            </Reveal>
          </div>
        </div>

        <figure className="chart-frame mt-12">
          <CandleField className="h-auto w-full" />
          <figcaption className="flex items-baseline gap-3 border-t border-line px-4 py-2.5">
            <span className="label-caps">The listed universe</span>
            <span className="num text-xs text-muted">
              The 50 largest ranked companies · one bar each · today's move, colored like the price charts
            </span>
          </figcaption>
        </figure>
      </div>
    </section>
  );
}

