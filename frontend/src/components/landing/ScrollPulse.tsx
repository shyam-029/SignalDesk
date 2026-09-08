import { motion, useScroll, useSpring, useTransform } from "framer-motion";

import { useReducedMotionSafe } from "@/components/motion/Reveal";
import { useTheme } from "@/components/layout/ThemeProvider";

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
 * Price-chart color language for the scroll rail: at the top of the page
 * (progress 0, the "valley") the point reads red, and as the user scrolls
 * down the hue travels gradually through amber to green - the same red-to-
 * green reading a price chart uses. The palettes are tuned per theme: the
 * dark theme carries the warmer saturated set, the light theme the deeper
 * print-like set. The drawn line keeps a two-stop gradient so the stroke
 * itself also shifts as it extends.
 */
const DARK = { red: "#e0654a", amber: "#e3b34c", green: "#37a583" };
const LIGHT = { red: "#bd5327", amber: "#b8862f", green: "#2d8a68" };

function colorAt(t: number, p: typeof DARK): string {
  // Two-segment interpolation red -> amber -> green.
  const [from, to, f] =
    t < 0.5 ? [p.red, p.amber, t / 0.5] : [p.amber, p.green, (t - 0.5) / 0.5];
  const mix = (a: string, b: string): string => {
    const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
    const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
    const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * f));
    return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
  };
  return mix(from, to);
}

/**
 * Fixed right rail: a faint track line, a gradient line drawing over it with
 * scroll progress, and a point whose color travels red -> amber -> green with
 * the same progress. Desktop only, decorative, pointer-transparent; hidden
 * under reduced motion.
 */
export function ScrollPulse() {
  const reduced = useReducedMotionSafe();
  const { theme } = useTheme();
  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 110, damping: 26, mass: 0.35 });

  const dot = useTransform(progress, (t) => pointAt(t));
  const dotX = useTransform(dot, (p) => p[0]);
  const dotY = useTransform(dot, (p) => p[1]);
  const palette = theme === "dark" ? DARK : LIGHT;
  const dotColor = useTransform(progress, (t) => colorAt(t, palette));

  if (reduced) return null;

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed right-5 top-1/2 z-30 hidden -translate-y-1/2 lg:block"
    >
      <svg width="56" height="248" viewBox="0 0 56 248">
        <defs>
          <linearGradient id="scroll-pulse-grad" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor={palette.red} />
            <stop offset="50%" stopColor={palette.amber} />
            <stop offset="100%" stopColor={palette.green} />
          </linearGradient>
        </defs>
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
          stroke="url(#scroll-pulse-grad)"
          strokeWidth="1.6"
          strokeLinejoin="round"
          strokeLinecap="round"
          style={{ pathLength: progress }}
        />
        {/* Soft halo + point: color rides the scroll like a price chart. */}
        <motion.circle r="7" opacity="0.22" style={{ cx: dotX, cy: dotY, fill: dotColor }} />
        <motion.circle r="2.8" style={{ cx: dotX, cy: dotY, fill: dotColor }} />
      </svg>
    </div>
  );
}
