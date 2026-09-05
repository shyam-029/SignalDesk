import { motion, useScroll, useSpring, useTransform } from "framer-motion";

import { useReducedMotionSafe } from "@/components/motion/Reveal";

/**
 * A clean uniform sine wave: one frequency, constant amplitude, monotonic
 * descent. The path is sampled from the same function the dot interpolates,
 * so the point rides the drawn line exactly.
 */
const SAMPLES = 140;
const TOP = 12;
const BOTTOM = 236;
const WAVES = 2.25;

function railX(t: number): number {
  return 28 + 15 * Math.sin(2 * Math.PI * WAVES * t);
}

function railY(t: number): number {
  return TOP + (BOTTOM - TOP) * t;
}

const TS = Array.from({ length: SAMPLES + 1 }, (_, i) => i / SAMPLES);
const POINTS: Array<[number, number]> = TS.map((t) => [railX(t), railY(t)]);
const PATH = `M${POINTS.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" L")}`;

/** Cumulative arc length for exact dot travel along the drawn curve. */
const CUM = POINTS.reduce<Array<number>>((acc, p, i) => {
  if (i === 0) return [0];
  const [px, py] = POINTS[i - 1];
  acc.push(acc[i - 1] + Math.hypot(p[0] - px, p[1] - py));
  return acc;
}, []);
const TOTAL = CUM[CUM.length - 1];

function pointAt(t: number): [number, number] {
  const d = Math.min(Math.max(t, 0), 1) * TOTAL;
  let i = 1;
  while (i < CUM.length - 1 && CUM[i] < d) i++;
  const span = CUM[i] - CUM[i - 1] || 1;
  const f = (d - CUM[i - 1]) / span;
  return [
    POINTS[i - 1][0] + (POINTS[i][0] - POINTS[i - 1][0]) * f,
    POINTS[i - 1][1] + (POINTS[i][1] - POINTS[i - 1][1]) * f,
  ];
}

/**
 * Fixed right rail: a faint track line, the gold line drawing over it with
 * scroll progress, and a soft-halo point riding the exact curve position.
 * Desktop only, decorative, pointer-transparent; hidden under reduced motion.
 */
export function ScrollPulse() {
  const reduced = useReducedMotionSafe();
  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 110, damping: 26, mass: 0.35 });

  const dot = useTransform(progress, (t) => pointAt(t));
  const dotX = useTransform(dot, (p) => p[0]);
  const dotY = useTransform(dot, (p) => p[1]);

  if (reduced) return null;

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed right-5 top-1/2 z-30 hidden -translate-y-1/2 lg:block"
    >
      <svg width="56" height="248" viewBox="0 0 56 248">
        <path
          d={PATH}
          fill="none"
          stroke="var(--rule)"
          strokeWidth="1"
          opacity="0.28"
          strokeLinejoin="round"
        />
        <motion.path
          d={PATH}
          fill="none"
          stroke="var(--cobalt)"
          strokeWidth="1.6"
          strokeLinejoin="round"
          strokeLinecap="round"
          style={{ pathLength: progress }}
        />
        {/* Soft halo + point */}
        <motion.circle r="7" fill="var(--cobalt)" opacity="0.22" style={{ cx: dotX, cy: dotY }} />
        <motion.circle r="2.8" fill="var(--cobalt)" style={{ cx: dotX, cy: dotY }} />
      </svg>
    </div>
  );
}
