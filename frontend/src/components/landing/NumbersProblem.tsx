import { motion } from "framer-motion";

import { Reveal } from "@/components/motion/Reveal";

/**
 * NumbersProblem — the editorial "the market is full of numbers" moment.
 * Loose, disconnected metric fragments drift in first; then the copy turns and
 * the same fragments reorganize into a structured column — the transition from
 * raw numbers to research structure, choreographed by scroll.
 */
const RAW_METRICS: Array<{ k: string; v: string }> = [
  { k: "P/E", v: "16.4" },
  { k: "ROE", v: "47.7%" },
  { k: "D/E", v: "0.31" },
  { k: "RSI 14", v: "38.6" },
  { k: "MACD", v: "−4.1" },
  { k: "EV/EBITDA", v: "10.8" },
  { k: "Op margin", v: "24.1%" },
  { k: "P/B", v: "2.41" },
  { k: "Net mgn", v: "19.4%" },
  { k: "SMA 20", v: "102.8" },
  { k: "P/S", v: "1.92" },
  { k: "Coverage", v: "11.2×" },
];

export function NumbersProblem() {
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 md:px-6 md:py-28">
        {/* Phase 1 — the flood of disconnected numbers. */}
        <Reveal>
          <h2 className="max-w-2xl font-display text-3xl font-semibold leading-tight md:text-4xl">
            The market is full of numbers.
          </h2>
          <p className="mt-4 max-w-xl text-muted">
            Every platform shows you the same figures. Pasted across tickers, feeds and
            screens — plentiful, precise, and disconnected.
          </p>
        </Reveal>

        <div className="relative mt-12">
          <RawCloud />
        </div>

        {/* Phase 2 — the turn. */}
        <Reveal className="mt-20 text-center md:mt-28">
          <p className="font-display text-xl text-muted md:text-2xl">
            Most platforms stop at showing them.
          </p>
          <p className="mt-6 font-display text-2xl font-semibold md:text-4xl">
            SignalDesk asks what they <span className="text-cobalt dark:text-cobalt-strong">mean</span>.
          </p>
        </Reveal>

        {/* Phase 3 — the same numbers, organized into a research structure. */}
        <div className="mt-14 grid gap-px border border-line bg-line md:grid-cols-2">
          <StructureRow
            title="Into fundamentals"
            items={["ROE 47.7%", "Op margin 24.1%", "D/E 0.31", "Coverage 11.2×"]}
            caption="→ Profitability 98 · Solvency 100"
          />
          <StructureRow
            title="Into valuation"
            items={["P/E 16.4", "EV/EBITDA 10.8", "P/B 2.41", "P/S 1.92"]}
            caption="→ vs same-industry peer medians"
          />
          <StructureRow
            title="Into technicals"
            items={["SMA 20 102.8", "RSI 14 38.6", "MACD −4.1"]}
            caption="→ Trend 31 · Momentum 4 · Reversion 46"
          />
          <StructureRow
            title="Into sentiment"
            items={["219 positive", "159 negative", "623 neutral"]}
            caption="→ FinBERT-scored news, net tone"
          />
        </div>
      </div>
    </section>
  );
}

function StructureRow({
  title,
  items,
  caption,
}: {
  title: string;
  items: string[];
  caption: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      className="bg-surface p-5"
    >
      <p className="label-caps">{title}</p>
      <div className="num mt-3 flex flex-wrap gap-2">
        {items.map((item) => (
          <span key={item} className="border border-line bg-background px-2 py-1 text-xs">
            {item}
          </span>
        ))}
      </div>
      <p className="num mt-3 text-xs text-cobalt dark:text-cobalt-strong">{caption}</p>
    </motion.div>
  );
}

/**
 * The disconnected-numbers cloud. Each chip drifts into its spot once, on
 * view — no infinite loops, no parallax; the disorder itself is the message.
 */
function RawCloud() {
  return (
    <>
      {RAW_METRICS.map((m, i) => {
        const drift = RAW_POSITIONS[i];
        return (
          <motion.span
            key={m.k}
            initial={{ opacity: 0, x: drift.dx * 40, y: drift.dy * 40, rotate: drift.r }}
            whileInView={{ opacity: 1, x: 0, y: 0, rotate: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.9, delay: i * 0.05, ease: [0.22, 1, 0.36, 1] }}
            className="num inline-flex items-baseline gap-1.5 border border-line bg-surface px-3 py-2 text-xs text-muted"
            style={{ margin: "4px 6px" }}
          >
            <span className="text-[10px] uppercase tracking-wide text-faint">{m.k}</span>
            <span className="font-medium">{m.v}</span>
          </motion.span>
        );
      })}
    </>
  );
}

const RAW_POSITIONS = RAW_METRICS.map((_, i) => ({
  dx: ((i * 37) % 11) - 5,
  dy: ((i * 53) % 7) - 3,
  r: (((i * 29) % 9) - 4) * 0.6,
}));

