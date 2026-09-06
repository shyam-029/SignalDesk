import { Reveal } from "@/components/motion/Reveal";

/**
 * Explainer section for the written research conclusion. The LLM is part of
 * the research workflow: it narrates only allow-listed SignalDesk facts. No
 * chat windows, no robot imagery, no "AI-powered" clichés.
 */
export function ExplainerSection() {
  return (
    <section className="section-alt relative border-b border-line">
      {/* Depth wash: a faint teal pool behind the conclusion card. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(560px 300px at 72% 40%, color-mix(in srgb, var(--accent-teal) 6%, transparent), transparent 72%)",
        }}
      />
      <div className="relative mx-auto max-w-6xl px-4 py-20 md:px-6 md:py-28">
        <div className="grid gap-12 lg:grid-cols-12">
          <Reveal className="lg:col-span-5">
            <p className="label-caps mb-3">Research, explained</p>
            <h2 className="font-display text-3xl font-semibold leading-tight md:text-4xl">
              A green number isn't an investment thesis.
            </h2>
            <p className="mt-4 text-muted">
              Every analytical conclusion in SignalDesk can explain itself: plain
              language, <span className="hi">traceable to the exact inputs</span> that produced it. The explanation
              model sees <span className="hi">only the computed facts</span>, never free text; if the model is
              unavailable, a rule-based narration of the same facts takes over.
            </p>
            <div className="num mt-8 space-y-2 text-xs text-muted">
              <p className="flex items-center gap-2">
                <span className="inline-block h-1 w-1 bg-cobalt" />
                Data, signal, explanation
              </p>
            </div>
          </Reveal>

          <Reveal delay={0.1} className="lg:col-span-7">
            <div className="glass">
              <div className="border-b border-line px-5 py-3">
                <p className="label-caps">Research conclusion · Reliance Industries</p>
              </div>
              <div className="space-y-4 px-5 py-5">
                <div className="num flex flex-wrap gap-2">
                  {["Alpha 59/100", "Fundamental 98", "Technical 27", "Sentiment 39"].map(
                    (chip) => (
                      <span
                        key={chip}
                        className="border border-line bg-background px-2 py-1 text-xs"
                      >
                        {chip}
                      </span>
                    ),
                  )}
                </div>
                <div className="border-l-2 border-cobalt pl-4 dark:border-cobalt-strong">
                  <p className="text-sm leading-relaxed">
                    Strong fundamentals are offset by weak price momentum. The stock trades
                    below its short-term trend, which keeps the composite score moderate
                    despite healthy profitability and solvency.
                  </p>
                </div>
                <p className="text-xs text-faint">
                  Generated from SignalDesk data. Not investment advice.
                </p>
              </div>
            </div>
            <p className="mt-3 text-xs leading-relaxed text-muted">
              In the product, this appears wherever a score appears: a
              <span className="text-foreground"> Why?</span> affordance next to the number it
              explains.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
