import { Link } from "react-router-dom";

import { useStockList } from "@/lib/hooks";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * TickerTape: the landing page's opening strip - the 50 largest ranked
 * companies, each with its day's move, in a continuous slow scroll. Real
 * stored data (daily close); red below, green above. A second, reversed
 * copy fills the loop so the animation is seamless. Pauses on hover.
 */
export function TickerTape() {
  const list = useStockList(1, 50, undefined, "market_cap", "desc");
  const items = (list.data?.items ?? []).filter((s) => s.change_pct != null);
  if (items.length === 0) return null;

  const doubled = [...items, ...items];

  return (
    <div
      className="group overflow-hidden border-b border-line bg-surface"
      aria-label="The 50 largest companies and today's moves"
    >
      <div
        className="flex w-max animate-[ticker_70s_linear_infinite] gap-8 py-2 group-hover:[animation-play-state:paused]"
        style={{ animationName: "ticker" }}
      >
        {doubled.map((s, i) => (
          <Link
            key={`${s.symbol}-${i}`}
            to={`/stocks/${encodeURIComponent(s.symbol)}`}
            className="num flex shrink-0 items-baseline gap-2 text-xs"
          >
            <span className="font-semibold text-foreground">{s.symbol.replace(".NS", "")}</span>
            <span>{fmtPrice(s.last_price)}</span>
            <span
              className={cn(
                "font-medium",
                (s.change_pct ?? 0) >= 0 ? "text-band-positive" : "text-band-weak",
              )}
            >
              {fmtSignedPct(s.change_pct)}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
