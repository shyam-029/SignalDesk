import { motion } from "framer-motion";

import { useReducedMotionSafe } from "@/components/motion/Reveal";

const EASE = [0.22, 1, 0.36, 1] as const;

const DIGITS = [
  { x: 96, y: 36, t: "16.4", tone: "var(--accent-amber)" },
  { x: 96, y: 63, t: "47.7", tone: "var(--accent-jade)" },
  { x: 96, y: 90, t: "38.6", tone: "var(--accent-coral)" },
];

/**
 * Three equal-length flow lines (symmetric around y=71), one per research
 * dimension and colored to match its metric, converging to the exact point
 * where the signal line begins.
 */
const FLOWS = [
  {
    d: "M110,44 C 190,44 250,71 310,71",
    tone: "var(--accent-amber)",
  },
  {
    d: "M110,71 C 190,71 250,71 310,71",
    tone: "var(--accent-jade)",
  },
  {
    d: "M110,98 C 190,98 250,71 310,71",
    tone: "var(--accent-coral)",
  },
];

/** A stylized close series starting exactly where the flows converge. */
const PULSE = "M310,71 L348,58 L382,66 L418,44 L452,52 L488,32 L522,42 L560,24";

/**
 * Pictographic "raw numbers to signal" diagram. Mono digits and flow lines
 * draw in on scroll; the analytical line resolves into a cobalt point.
 * With prefers-reduced-motion the fully drawn diagram renders statically.
 */
export function NumbersToSignal({ className }: { className?: string }) {
  const reduced = useReducedMotionSafe();

  const draw = (delay: number) =>
    reduced
      ? {}
      : {
          initial: { pathLength: 0, opacity: 0 },
          whileInView: { pathLength: 1, opacity: 1 },
          viewport: { once: true, margin: "-60px" },
          transition: { duration: 0.9, delay, ease: EASE },
        };

  const fade = (delay: number) =>
    reduced
      ? {}
      : {
          initial: { opacity: 0 },
          whileInView: { opacity: 1 },
          viewport: { once: true, margin: "-60px" },
          transition: { duration: 0.5, delay },
        };

  return (
    <svg
      viewBox="0 0 640 140"
      className={className}
      role="img"
      aria-label="Raw numbers flow into one analytical signal"
    >
      {/* Baseline rule */}
      <line x1="16" y1="132" x2="624" y2="132" stroke="var(--line)" strokeWidth="1" />

      {/* Raw mono inputs, right-aligned against the flow starts */}
      {DIGITS.map((d, i) => (
        <motion.text
          key={d.t}
          x={d.x}
          y={d.y}
          textAnchor="end"
          fill={d.tone}
          fontSize="12"
          fontWeight="600"
          fontFamily="var(--font-mono)"
          {...fade(0.1 + i * 0.12)}
        >
          {d.t}
        </motion.text>
      ))}
      <motion.text
        x="34"
        y="20"
        fill="var(--faint)"
        fontSize="12"
        fontFamily="var(--font-sans)"
        letterSpacing="2"
        {...fade(0.05)}
      >
        RAW
      </motion.text>

      {/* Converging flows, one per dimension */}
      {FLOWS.map((f, i) => (
        <motion.path
          key={f.d}
          d={f.d}
          fill="none"
          stroke={f.tone}
          strokeWidth="1.4"
          strokeLinecap="round"
          {...draw(0.3 + i * 0.15)}
        />
      ))}

      {/* The signal */}
      <motion.path
        d={PULSE}
        fill="none"
        stroke="var(--cobalt)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        {...draw(0.75)}
      />
      <motion.circle
        cx="560"
        cy="24"
        r="4"
        fill="var(--cobalt)"
        {...fade(1.55)}
      />
      <motion.text
        x="572"
        y="28"
        fill="var(--ink)"
        fontSize="12"
        fontWeight="600"
        fontFamily="var(--font-sans)"
        letterSpacing="2"
        {...fade(1.6)}
      >
        SIGNAL
      </motion.text>
    </svg>
  );
}
