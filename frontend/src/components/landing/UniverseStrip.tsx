import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import { useStockList } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { Reveal } from "@/components/motion/Reveal";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The household names to feature first (they exist in the Nifty 50 catalog). */
const FEATURED = new Set([
  "TCS",
  "RELIANCE",
  "HDFCBANK",
  "INFY",
  "ICICIBANK",
  "BHARTIARTL",
  "SBIN",
  "LT",
]);

/**
 * UniverseStrip — the research universe, from the live catalog. These are
 * research subjects, not customers: no "trusted by" language, no logos.
 */
export function UniverseStrip() {
  const list = useStockList(1, 200);

  const featured = list.data
    ? list.data.items.filter((s) => FEATURED.has(s.symbol.replace(".NS", "")))
    : [];

  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 md:px-6 md:py-28">
        <Reveal className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="label-caps mb-3">The research universe</p>
            <h2 className="max-w-2xl font-display text-3xl font-semibold leading-tight md:text-4xl">
              Research the companies that matter.
            </h2>
          </div>
          <p className="text-xs text-muted">
            {list.data ? (
              <>
                <span className="num font-semibold text-foreground">{list.data.total}</span>{" "}
                companies · Nifty 50 today, built to scale toward Nifty 500
              </>
            ) : (
              "Nifty 50 universe · Yahoo Finance data"
            )}
          </p>
        </Reveal>

        <Reveal delay={0.08} className="mt-10">
          <DataState
            loading={list.isLoading}
            error={list.error}
            onRetry={list.refetch}
            empty={!list.data || list.data.items.length === 0}
            skeleton={
              <div className="grid gap-px bg-line sm:grid-cols-2 md:grid-cols-4">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="h-24 animate-pulse bg-surface" />
                ))}
              </div>
            }
          >
            <div className="grid gap-px border border-line bg-line sm:grid-cols-2 md:grid-cols-4">
              {featured.map((s) => (
                <Link
                  key={s.symbol}
                  to={`/stocks/${s.symbol.replace(".NS", "")}`}
                  className="group bg-surface px-5 py-4 transition-colors hover:bg-surface-2"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="num text-xs font-semibold">{s.symbol.replace(".NS", "")}</span>
                    <span
                      className={cn(
                        "num text-[11px]",
                        s.change_pct >= 0 ? "text-band-positive" : "text-band-weak",
                      )}
                    >
                      {fmtSignedPct(s.change_pct)}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-sm font-medium">{s.name}</p>
                  <p className="num mt-1 text-xs text-muted">{fmtPrice(s.last_price)}</p>
                </Link>
              ))}
            </div>
          </DataState>
          <div className="mt-4 flex justify-end">
            <Link
              to="/markets"
              className="inline-flex items-center gap-1 text-xs text-cobalt hover:underline dark:text-cobalt-strong"
            >
              Browse the full universe
              <ArrowRight className="size-3.5" />
            </Link>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
