import * as React from "react";
import { motion } from "framer-motion";

import { Reveal, useReducedMotionSafe } from "@/components/motion/Reveal";
import { cn } from "@/lib/utils";

/**
 * Framework: the analytical framework, four inputs converging into one score.
 * The cards are clickable: selecting a dimension highlights it, tints the
 * composite readout, and dims the other weight rows. The relationship (inputs
 * converging) is the composition; this is not a four-card feature grid.
 */

const DIMENSIONS: Array<{
  title: string;
  accentVar: string;
  question: string;
  metrics: Array<[string, string]>;
  note: string | null;
  weight: string | null;
}> = [  {
    title: "Fundamentals",
    accentVar: "var(--accent-jade)",
    question: "How strong is the business?",
    metrics: [["ROE", "47.7%"], ["D/E", "0.31"], ["Op margin", "24.1%"]],
    note: "Profitability 98 · Solvency 100",
    weight: "Fundamental",
  },
  {
    title: "Valuation",
    accentVar: "var(--accent-amber)",
    question: "What does the market charge?",
    metrics: [["P/E", "16.56"], ["EV/EBITDA", "10.84"], ["P/B", "2.41"], ["P/S", "1.92"]],
    note: "Assessed separately, never blended into Alpha",
    weight: null,
  },
  {
    title: "Technicals",
    accentVar: "var(--accent-coral)",
    question: "How is price positioned?",
    metrics: [["SMA 20", "below"], ["RSI 14", "38.6"], ["MACD", "negative"]],
    note: "Heuristic read · not predictive",
    weight: "Technical",
  },
  {
    title: "Sentiment",
    accentVar: "var(--accent-teal)",
    question: "What is the news tone?",
    metrics: [["Articles", "1,001"], ["Positive", "219"], ["Negative", "159"]],
    note: null,
    weight: "Sentiment",
  },
];

export function Framework() {
  const [active, setActive] = React.useState<number | null>(null);

  const toggle = (i: number) => setActive((cur) => (cur === i ? null : i));

  return (
    <section id="how-it-works" className="relative border-b border-line bg-surface-2/40">
      {/* Depth wash: a faint cool pool behind the convergence panel. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(640px 320px at 78% 46%, color-mix(in srgb, var(--cobalt) 6%, transparent), transparent 72%)",
        }}
      />
      <div className="relative mx-auto max-w-6xl px-4 py-20 md:px-6 md:py-28">
        <Reveal>
          <p className="label-caps mb-3">The analytical framework</p>
          <h2 className="max-w-2xl font-display text-3xl font-semibold leading-tight md:text-4xl">
            Four independent analyses. One signal.
          </h2>
          <p className="mt-4 max-w-xl text-muted">
            Each dimension answers a different question: how strong the business is, what the
            market charges for it, how the price is positioned, and what the news says. None
            of them is a recommendation alone.
          </p>
        </Reveal>

        <div className="mt-14 grid items-center gap-8 lg:grid-cols-12">
          {/* Inputs */}
          <div className="grid gap-px bg-line sm:grid-cols-2 lg:col-span-7">
            {DIMENSIONS.map((d, i) => (
              <InputCard
                key={d.title}
                title={d.title}
                accentVar={d.accentVar}
                question={d.question}
                metrics={[...d.metrics]}
                note={d.note}
                selected={active === i}
                dimmed={active != null && active !== i}
                onSelect={() => toggle(i)}
              />
            ))}
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
              className="glass w-full max-w-sm p-5"
              style={{
                borderColor:
                  active != null
                    ? colorMix(DIMENSIONS[active].accentVar, 55)
                    : colorMix("var(--band-moderate)", 40),
              }}
            >
              <div className="flex items-baseline justify-between">
                <p className="label-caps">Alpha Score</p>
                <span className="label-caps">Composite</span>
              </div>
              <p className="num mt-2 text-5xl font-medium text-band-moderate">
                59<span className="ml-1 text-base text-faint">/100</span>
              </p>
              <div className="mt-4 space-y-2">
                {DIMENSIONS.filter((d) => d.weight).map((d) => {
                  const value = d.title === "Fundamentals" ? 98 : d.title === "Technicals" ? 27 : 39;
                  const weight = d.title === "Fundamentals" ? "40%" : "30%";
                  const tone =
                    d.title === "Fundamentals"
                      ? "var(--band-strong)"
                      : "var(--band-weak)";
                  return (
                    <WeightRow
                      key={d.title}
                      name={d.weight!}
                      accentVar={d.accentVar}
                      value={value}
                      weight={weight}
                      tone={tone}
                      highlighted={active != null && DIMENSIONS[active].weight === d.weight}
                      dimmed={active != null && DIMENSIONS[active].weight !== d.weight}
                    />
                  );
                })}
              </div>
              <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-faint">
                Weights renormalize over available components. Valuation stays separate.
              </p>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}

/** color-mix helper for accent borders (kept as a string for inline styles). */
function colorMix(v: string, pct: number): string {
  return `color-mix(in srgb, ${v} ${pct}%, transparent)`;
}

function InputCard({
  title,
  question,
  metrics,
  note,
  accentVar,
  selected,
  dimmed,
  onSelect,
}: {
  title: string;
  question: string;
  metrics: Array<[string, string]>;
  note?: string | null;
  accentVar: string;
  selected: boolean;
  dimmed: boolean;
  onSelect: () => void;
}) {
  const reduced = useReducedMotionSafe();
  return (
    <motion.button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      whileHover={reduced ? undefined : { y: -3 }}
      className={cn(
        "bg-surface p-5 text-left outline-none transition-[background-color,border-color,opacity] duration-200",
        "focus-visible:border-cobalt",
        dimmed && "opacity-45",
      )}
      style={{
        borderTop: `2px solid ${colorMix(accentVar, selected ? 100 : 45)}`,
        backgroundColor: selected ? colorMix(accentVar, 6) : undefined,
      }}
    >
      <p className="label-caps flex items-center gap-1.5">
        <span
          className="inline-block size-1.5 rounded-full"
          style={{ background: accentVar }}
          aria-hidden
        />
        <span style={{ color: selected ? accentVar : undefined }}>{title}</span>
      </p>
      <p className="mt-1 text-sm font-medium">{question}</p>
      <div className="num mt-3 space-y-1">
        {metrics.map(([k, v]) => (
          <div key={k} className="flex justify-between text-xs">
            <span className="text-faint">{k}</span>
            <span className="font-medium">{v}</span>
          </div>
        ))}
      </div>
      {note && <p className="mt-3 text-xs italic text-faint">{note}</p>}
    </motion.button>
  );
}

function WeightRow({
  name,
  value,
  weight,
  tone,
  accentVar,
  highlighted,
  dimmed,
}: {
  name: string;
  value: number;
  weight: string;
  tone: string;
  accentVar: string;
  highlighted: boolean;
  dimmed: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 transition-opacity duration-200",
        highlighted && "opacity-100",
        dimmed && "opacity-35",
      )}
    >
      <span
        className="w-20 text-xs font-medium"
        style={{ color: highlighted ? accentVar : "var(--muted)" }}
      >
        {name}
      </span>
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
      <span className="num w-8 text-right text-xs text-faint">{weight}</span>
    </div>
  );
}
