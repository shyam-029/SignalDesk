import { Link } from "react-router-dom";

import { useNifty50 } from "@/lib/nifty50";
import { useReducedMotionSafe } from "@/components/motion/Reveal";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * TickerTape: the landing page's opening strip. The Nifty 50 constituents,
 * each with its stored close and the day's move, in one slow continuous
 * scroll. Real stored data; every ticker links to its research page. The
 * list is doubled so the loop is seamless. Pauses on hover; a plain
 * scrollable row under reduced motion.
 */
export function TickerTape() {
  const { items } = useNifty50();
  const reduced = useReducedMotionSafe();
  if (items.length === 0) return null;

  const loop = reduced ? items : [...items, ...items];

  return (
    <div
      className={cn(
        "group border-b border-line bg-surface",
        reduced ? "overflow-x-auto" : "overflow-hidden",
      )}
      aria-label="Nifty 50 companies and today's moves"
    >
      <div
        className={cn(
          "flex w-max gap-8 px-4 py-2",
          !reduced && "group-hover:[animation-play-state:paused]",
        )}
        style={reduced ? undefined : { animation: "ticker 90s linear infinite" }}
      >
        {loop.map((s, i) => (
          <Link
            key={`${s.symbol}-${i}`}
            to={`/stocks/${encodeURIComponent(s.symbol.replace(".NS", ""))}`}
            aria-hidden={i >= items.length}
            tabIndex={i >= items.length ? -1 : undefined}
            className="num flex shrink-0 items-baseline gap-2 text-xs text-muted transition-colors hover:text-foreground"
          >
            <span className="tkr text-foreground">{s.symbol.replace(".NS", "")}</span>
            <span>{fmtPrice(s.last_price)}</span>
            <span className={cn("font-medium", (s.change_pct ?? 0) >= 0 ? "text-up" : "text-down")}>
              {fmtSignedPct(s.change_pct)}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
