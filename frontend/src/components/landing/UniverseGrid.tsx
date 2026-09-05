import { motion } from "framer-motion";

import { useReducedMotionSafe } from "@/components/motion/Reveal";

/**
 * The listed universe as fifty equal bars, one per Nifty 50 constituent
 * (illustrative): a symmetric, full-width field. Most bars are neutral; four
 * carry the dimension accents and one the identity gold. Bars lift on hover.
 * Opacity/transform only; static under prefers-reduced-motion.
 */
const N = 50;
const STEP = 24;
const WIDTH = N * STEP;
const BASE = 196;
const MAX_H = 168;

const TONES: Record<number, string> = {
  7: "var(--accent-jade)",
  18: "var(--accent-amber)",
  29: "var(--accent-coral)",
  41: "var(--accent-teal)",
  46: "var(--cobalt)",
};

/** Deterministic height wave, same on every render (no randomness). */
function barHeight(i: number): number {
  const wave = Math.abs(Math.sin(i * 0.55));
  const steps = ((i * 7) % 5) * 4;
  return Math.round(44 + wave * 96 + steps);
}

export function UniverseGrid({ className }: { className?: string }) {
  const reduced = useReducedMotionSafe();

  return (
    <svg
      viewBox={`0 0 ${WIDTH} 240`}
      className={className}
      role="img"
      aria-label="Fifty equal bars, one per Nifty 50 constituent, a few carrying dimension accents"
    >
      {/* Baseline */}
      <line x1="0" y1={BASE + 2} x2={WIDTH} y2={BASE + 2} stroke="var(--line)" strokeWidth="1" />
      {Array.from({ length: N }, (_, i) => {
        const h = Math.min(barHeight(i), MAX_H);
        const x = i * STEP + 4;
        const y = BASE - h;
        const tone = TONES[i];
        return (
          <motion.rect
            key={i}
            x={x}
            y={y}
            width={STEP - 8}
            height={h}
            rx="1"
            fill={tone ?? "var(--rule)"}
            fillOpacity={tone ? 0.3 : 0.5}
            stroke={tone ?? "var(--rule)"}
            strokeOpacity={tone ? 0.8 : 1}
            strokeWidth="1"
            whileHover={
              reduced
                ? undefined
                : {
                    y: y - 6,
                    fillOpacity: tone ? 0.5 : 0.9,
                    transition: { duration: 0.15 },
                  }
            }
            {...(reduced
              ? {}
              : {
                  initial: { opacity: 0, y: BASE },
                  whileInView: { opacity: 1, y },
                  viewport: { once: true, margin: "-60px" },
                  transition: { duration: 0.45, delay: 0.1 + i * 0.014, ease: [0.22, 1, 0.36, 1] },
                })}
            style={{ cursor: "default" }}
          />
        );
      })}
    </svg>
  );
}
