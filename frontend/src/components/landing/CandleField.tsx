import * as React from "react";
import { motion } from "framer-motion";

import { useStockList } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { useReducedMotionSafe } from "@/components/motion/Reveal";
import { fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * The listed universe, finished: the 50 LARGEST ranked companies (the Nifty
 * 50 in spirit) as one bar each, sized by the day's absolute move and
 * colored by its sign - red below, green above, exactly like the price
 * charts. Real stored data, hover for the readout; illustrative framing
 * removed now that the bars are the market itself.
 */
export function CandleField({ className }: { className?: string }) {
  const reduced = useReducedMotionSafe();
  const [active, setActive] = React.useState<number | null>(null);
  const list = useStockList(1, 50, undefined, "market_cap", "desc");
  const items = (list.data?.items ?? []).filter((s) => s.change_pct != null);

  const W = 1200;
  const H = 320;
  const BASE = 160; // zero-change midline: red below, green above
  const n = Math.max(items.length, 1);
  const step = W / n;
  const maxAbs = Math.max(0.5, ...items.map((s) => Math.abs(s.change_pct ?? 0)));

  const activeItem = active != null ? items[active] : null;

  return (
    <div className={cn("relative", className)}>
      <DataState
        loading={list.isLoading}
        error={list.error}
        onRetry={list.refetch}
        skeleton={<div className="h-72 w-full animate-pulse bg-surface-2" />}
        empty={!list.data || items.length === 0}
      >
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full"
          role="img"
          aria-label="The 50 largest ranked companies, one bar each, sized by today's absolute move and colored by its sign."
        >
          {/* Zero line + hairline grid */}
          <line x1="0" y1={BASE} x2={W} y2={BASE} stroke="var(--line)" strokeWidth="1" />
          {[60, 110, 210, 260].map((y) => (
            <line key={y} x1="0" y1={y} x2={W} y2={y} stroke="var(--line)" strokeWidth="0.5" opacity="0.5" />
          ))}

          {items.map((s, i) => {
            const change = s.change_pct ?? 0;
            const up = change >= 0;
            const h = Math.max(4, (Math.abs(change) / maxAbs) * 130);
            const x = i * step + step * 0.2;
            const barW = step * 0.6;
            const y = up ? BASE - h : BASE;
            const isActive = i === active;
            return (
              <motion.rect
                key={s.symbol}
                x={x}
                y={y}
                width={barW}
                height={h}
                rx="1.5"
                fill={up ? "var(--band-positive)" : "var(--band-weak)"}
                fillOpacity={isActive ? 0.95 : 0.55}
                stroke={up ? "var(--band-positive)" : "var(--band-weak)"}
                strokeOpacity={isActive ? 1 : 0.7}
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive((cur) => (cur === i ? null : cur))}
                style={{ cursor: "crosshair" }}
                {...(reduced
                  ? {}
                  : {
                      initial: { opacity: 0, scaleY: 0.4 },
                      whileInView: { opacity: 1, scaleY: 1 },
                      viewport: { once: true, margin: "-40px" },
                      transition: { duration: 0.5, delay: i * 0.012, ease: EASE },
                    })}
              />
            );
          })}
        </svg>

        {/* Readout */}
        <div className="num absolute right-3 top-3 border border-line bg-background/90 px-2.5 py-1.5 text-xs text-muted">
          {activeItem ? (
            <>
              <span className="text-foreground">{activeItem.symbol.replace(".NS", "")}</span>
              {"  "}
              <span
                className={cn(
                  (activeItem.change_pct ?? 0) >= 0 ? "text-band-positive" : "text-band-weak",
                )}
              >
                {fmtSignedPct(activeItem.change_pct)}
              </span>
            </>
          ) : (
            "Hover a bar - the 50 largest, today's move"
          )}
        </div>
      </DataState>
    </div>
  );
}
