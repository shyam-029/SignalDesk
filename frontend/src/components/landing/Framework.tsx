import { motion } from "framer-motion";

import { Reveal } from "@/components/motion/Reveal";

/**
 * Framework — the analytical framework: four inputs converging into one score.
 * The relationship (inputs → convergence) is the composition; this is not a
 * four-card feature grid.
 */
export function Framework() {
  return (
    <section id="how-it-works" className="border-b border-line bg-surface-2/40">
      <div className="mx-auto max-w-6xl px-4 py-20 md:px-6 md:py-28">
        <Reveal>
          <p className="label-caps mb-3">The analytical framework</p>
          <h2 className="max-w-2xl font-display text-3xl font-semibold leading-tight md:text-4xl">
            Four independent analyses. One defensible signal.
          </h2>
          <p className="mt-4 max-w-xl text-muted">
            Each dimension answers a different question — how strong the business is, what the
            market charges for it, how the price is positioned, and what the news says. None
            of them is a recommendation alone.
          </p>
        </Reveal>

        <div className="mt-14 grid items-center gap-8 lg:grid-cols-12">
          {/* Inputs */}
          <div className="grid gap-px bg-line sm:grid-cols-2 lg:col-span-7">
            <InputCard
              title="Fundamentals"
              question="How strong is the business?"
              metrics={[["ROE", "47.7%"], ["D/E", "0.31"], ["Op margin", "24.1%"]]}
              note="→ Profitability 98 · Solvency 100"
            />
            <InputCard
              title="Valuation"
              question="What does the market charge?"
              metrics={[["P/E", "16.56"], ["EV/EBITDA", "10.84"], ["P/B", "2.41"], ["P/S", "1.92"]]}
              note="Assessed separately — never blended into Alpha"
            />
            <InputCard
              title="Technicals"
              question="How is price positioned?"
              metrics={[["SMA 20", "below"], ["RSI 14", "38.6"], ["MACD", "negative"]]}
              note="Heuristic read · not predictive"
            />
            <InputCard
              title="Sentiment"
              question="What is the news tone?"
              metrics={[["Articles", "1,001"], ["Positive", "219"], ["Negative", "159"]]}
            />
          </div>

          {/* Convergence: lines drawn from the four inputs into the score. */}
          <div className="relative flex flex-col items-center lg:col-span-5">
            <svg
              className="pointer-events-none absolute -left-4 top-1/2 hidden h-full w-10 -translate-y-1/2 lg:block"
              viewBox="0 0 40 240"
              aria-hidden
            >
              {[30, 90, 150, 210].map((y, i) => (
                <motion.path
                  key={y}
                  d={`M0,${y} C18,${y} 22,120 40,120`}
                  fill="none"
                  stroke="var(--rule)"
                  strokeWidth="1"
                  initial={{ pathLength: 0 }}
                  whileInView={{ pathLength: 1 }}
                  viewport={{ once: true, margin: "-120px" }}
                  transition={{ duration: 0.7, delay: 0.3 + i * 0.12 }}
                />
              ))}
            </svg>
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              whileInView={{ opacity: 1, scale: 1, y: 0 }}
              viewport={{ once: true, margin: "-120px" }}
              transition={{ duration: 0.6, delay: 0.55, ease: [0.22, 1, 0.36, 1] }}
              className="w-full max-w-sm border border-band-moderate/35 bg-band-moderate/5 p-5"
            >
              <div className="flex items-baseline justify-between">
                <p className="label-caps">Alpha Score</p>
                <span className="label-caps">Composite</span>
              </div>
              <p className="num mt-2 text-5xl font-medium text-band-moderate">
                59<span className="ml-1 text-base text-faint">/100</span>
              </p>
              <div className="mt-4 space-y-2">
                <WeightRow name="Fundamental" value={98} weight="40%" tone="var(--band-strong)" />
                <WeightRow name="Technical" value={27} weight="30%" tone="var(--band-weak)" />
                <WeightRow name="Sentiment" value={39} weight="30%" tone="var(--band-weak)" />
              </div>
              <p className="mt-4 border-t border-line pt-3 text-[11px] leading-relaxed text-faint">
                Weights renormalize over available components. Valuation stays separate.
              </p>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}

function InputCard({
  title,
  question,
  metrics,
  note,
}: {
  title: string;
  question: string;
  metrics: Array<[string, string]>;
  note?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="bg-surface p-5"
    >
      <p className="label-caps">{title}</p>
      <p className="mt-1 text-sm font-medium">{question}</p>
      <div className="num mt-3 space-y-1">
        {metrics.map(([k, v]) => (
          <div key={k} className="flex justify-between text-xs">
            <span className="text-faint">{k}</span>
            <span className="font-medium">{v}</span>
          </div>
        ))}
      </div>
      {note && <p className="mt-3 text-[11px] italic text-faint">{note}</p>}
    </motion.div>
  );
}

function WeightRow({
  name,
  value,
  weight,
  tone,
}: {
  name: string;
  value: number;
  weight: string;
  tone: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-20 text-xs text-muted">{name}</span>
      <div className="h-1.5 flex-1 bg-line">
        <motion.div
          className="h-full"
          style={{ background: tone }}
          initial={{ width: 0 }}
          whileInView={{ width: `${value}%` }}
          viewport={{ once: true, margin: "-120px" }}
          transition={{ duration: 0.9, delay: 0.7, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
      <span className="num w-10 text-right text-xs font-medium">{value}</span>
      <span className="num w-8 text-right text-[10px] text-faint">{weight}</span>
    </div>
  );
}
