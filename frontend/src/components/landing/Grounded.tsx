import { Reveal } from "@/components/motion/Reveal";

/**
 * Grounded — introduces the grounded research explanation. The LLM is part of
 * the research workflow: it narrates only allow-listed SignalDesk facts. No
 * chat windows, no robot imagery, no "AI-powered" clichés.
 */
export function Grounded() {
  return (
    <section className="border-b border-line bg-surface-2/40">
      <div className="mx-auto max-w-6xl px-4 py-20 md:px-6 md:py-28">
        <div className="grid gap-12 lg:grid-cols-12">
          <Reveal className="lg:col-span-5">
            <p className="label-caps mb-3">Grounded research</p>
            <h2 className="font-display text-3xl font-semibold leading-tight md:text-4xl">
              A green number isn't an investment thesis.
            </h2>
            <p className="mt-4 text-muted">
              Every analytical conclusion in SignalDesk can explain itself — in plain
              language, traceable to the exact inputs that produced it. The explanation
              model sees only the computed facts, never free text; if the model is
              unavailable, a rule-based narration of the same facts takes over.
            </p>
            <div className="num mt-8 space-y-2 text-xs text-muted">
              <p className="flex items-center gap-2">
                <span className="inline-block h-1 w-1 bg-cobalt" />
                Data → Signal → Explanation
              </p>
            </div>
          </Reveal>

          <Reveal delay={0.1} className="lg:col-span-7">
            <div className="border border-line bg-surface">
              <div className="border-b border-line px-5 py-3">
                <p className="label-caps">Research conclusion · Reliance Industries</p>
              </div>
              <div className="space-y-4 px-5 py-5">
                <div className="num flex flex-wrap gap-2">
                  {["Alpha 59/100", "Fundamental 98", "Technical 27", "Sentiment 39"].map(
                    (chip) => (
                      <span
                        key={chip}
                        className="border border-line bg-background px-2 py-1 text-[11px]"
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
                <p className="text-[11px] text-faint">
                  Generated explanation · grounded in SignalDesk data · not investment advice
                </p>
              </div>
            </div>
            <p className="mt-3 text-xs leading-relaxed text-muted">
              In the product, this appears wherever a score appears — as a quiet
              <span className="text-foreground"> Why?</span> affordance next to the number it
              explains.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
