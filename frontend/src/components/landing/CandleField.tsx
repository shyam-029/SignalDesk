import * as React from "react";
import { motion } from "framer-motion";

import { useReducedMotionSafe } from "@/components/motion/Reveal";
import { cn } from "@/lib/utils";

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * Hand-drawn candle field: an authored pictogram in the product's own visual
 * language (hairline grid, mono ticks, band-colored marks), NOT a photograph
 * and NOT real data; the caption labels it illustrative. Candles are
 * interactive: hovering (or tapping) highlights a bar and reads out its
 * illustrative OHLC. Opacity/transform animations only, so scrolling stays
 * cheap.
 */
const CANDLES: Array<{ x: number; o: number; c: number; hi: number; lo: number; tone?: string }> = [
  { x: 60, o: 232, c: 210, hi: 244, lo: 198 },
  { x: 104, o: 210, c: 224, hi: 232, lo: 202 },
  { x: 148, o: 224, c: 196, hi: 230, lo: 188 },
  { x: 192, o: 196, c: 214, hi: 222, lo: 190 },
  { x: 236, o: 214, c: 178, hi: 220, lo: 172 },
  { x: 280, o: 178, c: 152, hi: 186, lo: 144 },
  { x: 324, o: 152, c: 170, hi: 176, lo: 148 },
  { x: 368, o: 170, c: 138, hi: 176, lo: 132 },
  { x: 412, o: 138, c: 154, hi: 160, lo: 132 },
  { x: 456, o: 154, c: 118, hi: 158, lo: 112 },
  { x: 500, o: 118, c: 134, hi: 140, lo: 112 },
  { x: 544, o: 134, c: 100, hi: 138, lo: 94, tone: "var(--band-weak)" },
  { x: 588, o: 100, c: 118, hi: 124, lo: 96 },
  { x: 632, o: 118, c: 96, hi: 122, lo: 88 },
  { x: 676, o: 96, c: 112, hi: 118, lo: 90 },
  { x: 720, o: 112, c: 86, hi: 116, lo: 80 },
  { x: 764, o: 86, c: 104, hi: 110, lo: 82 },
  { x: 808, o: 104, c: 82, hi: 108, lo: 76 },
  { x: 852, o: 82, c: 98, hi: 104, lo: 78 },
  { x: 896, o: 98, c: 74, hi: 102, lo: 68 },
  { x: 940, o: 74, c: 92, hi: 98, lo: 70 },
  { x: 984, o: 92, c: 70, hi: 96, lo: 62 },
  { x: 1028, o: 70, c: 84, hi: 90, lo: 64 },
  { x: 1072, o: 84, c: 62, hi: 88, lo: 56 },
  { x: 1116, o: 62, c: 78, hi: 84, lo: 58 },
];

/** One analytic line threading the field, resolving to a gold point. */
const TREND = `M${CANDLES.map((k) => `${k.x},${(k.o + k.c) / 2}`).join(" L")}`;

const GRID_YS = [52, 96, 140, 184, 228, 272];

/** Map the drawing's vertical positions to plausible illustrative prices. */
const toPrice = (v: number) => Math.round((300 - v) * 9.5);

export function CandleField({ className }: { className?: string }) {
  const reduced = useReducedMotionSafe();
  const [active, setActive] = React.useState<number | null>(null);
  const k = active != null ? CANDLES[active] : null;

  const fade = (delay: number) =>
    reduced
      ? {}
      : {
          initial: { opacity: 0 },
          whileInView: { opacity: 1 },
          viewport: { once: true, margin: "-60px" },
          transition: { duration: 0.4, delay },
        };

  const draw = (delay: number) =>
    reduced
      ? {}
      : {
          initial: { pathLength: 0, opacity: 0 },
          whileInView: { pathLength: 1, opacity: 1 },
          viewport: { once: true, margin: "-60px" },
          transition: { duration: 1.4, delay, ease: EASE },
        };

  return (
    <div className={cn("relative", className)}>
      <svg
        viewBox="0 0 1200 340"
        className="h-auto w-full"
        role="img"
        aria-label="Illustrative candlestick field with an analytic line resolving to a signal point. Hover a candle for its illustrative values."
      >
        {/* Hairline grid */}
        <motion.g {...fade(0.05)} style={{ pointerEvents: "none" }}>
          {GRID_YS.map((y) => (
            <line key={y} x1="24" y1={y} x2="1176" y2={y} stroke="var(--line)" strokeWidth="1" />
          ))}
          <line x1="24" y1="20" x2="24" y2="320" stroke="var(--line)" strokeWidth="1" />
        </motion.g>

        {/* Crosshair guide for the active candle */}
        {k && (
          <line
            x1={k.x}
            y1="20"
            x2={k.x}
            y2="320"
            stroke="var(--rule)"
            strokeWidth="1"
            strokeDasharray="3 4"
            style={{ pointerEvents: "none" }}
          />
        )}

        {/* Candles: wick + body, mostly neutral, one band-colored inflection */}
        {CANDLES.map((candle, i) => {
          const isActive = i === active;
          const up = candle.c >= candle.o;
          const top = Math.min(candle.o, candle.c);
          const h = Math.max(Math.abs(candle.c - candle.o), 6);
          const stroke = isActive
            ? "var(--cobalt)"
            : (candle.tone ?? "var(--rule)");
          return (
            <motion.g
              key={candle.x}
              {...fade(0.15 + i * 0.035)}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive((cur) => (cur === i ? null : cur))}
              onClick={() => setActive((cur) => (cur === i ? null : i))}
              style={{ cursor: "crosshair" }}
            >
              <line
                x1={candle.x}
                y1={candle.hi}
                x2={candle.x}
                y2={candle.lo}
                stroke={stroke}
                strokeWidth={isActive ? 2 : 1.4}
                style={{ transition: "stroke 120ms linear" }}
              />
              <rect
                x={candle.x - 9}
                y={top}
                width="18"
                height={h}
                fill={
                  isActive
                    ? "var(--cobalt)"
                    : (candle.tone ?? (up ? "var(--surface-2)" : "var(--rule)"))
                }
                fillOpacity={isActive ? 0.25 : 1}
                stroke={stroke}
                strokeWidth={isActive ? 1.8 : 1.2}
                style={{ transition: "fill 120ms linear, stroke 120ms linear" }}
              />
            </motion.g>
          );
        })}

        {/* Analytic line over the field */}
        <motion.path
          d={TREND}
          fill="none"
          stroke="var(--cobalt)"
          strokeWidth="2.2"
          strokeLinejoin="round"
          strokeLinecap="round"
          style={{ pointerEvents: "none" }}
          opacity={reduced ? 1 : undefined}
          {...draw(0.7)}
        />
        <motion.circle
          cx="1116"
          cy="70"
          r="5"
          fill="var(--cobalt)"
          style={{ pointerEvents: "none" }}
          {...fade(2)}
        />
      </svg>

      {/* OHLC readout */}
      <div className="num absolute right-3 top-3 border border-line bg-background/90 px-2.5 py-1.5 text-xs text-muted">
        {k ? (
          <>
            <span className="text-foreground">O {toPrice(k.o).toLocaleString("en-IN")}</span>
            {"  H "}
            {toPrice(k.hi).toLocaleString("en-IN")}
            {"  L "}
            {toPrice(k.lo).toLocaleString("en-IN")}
            {"  C "}
            <span className="text-foreground">{toPrice(k.c).toLocaleString("en-IN")}</span>
          </>
        ) : (
          "Hover a candle for its illustrative values"
        )}
      </div>
    </div>
  );
}
