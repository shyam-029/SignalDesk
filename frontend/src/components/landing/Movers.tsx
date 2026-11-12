import { Link } from "react-router-dom";

import { useStockList } from "@/lib/hooks";
import type { StockSummary } from "@/lib/types";
import { DataState } from "@/components/data/DataState";
import { StockLogo } from "@/components/stock/StockLogo";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Movers: the day's five largest gains and five largest falls across the
 * ranked universe, from the stored daily close. Two server-sorted requests;
 * each row links to the company. The thin bar under a row is that move
 * relative to the largest move on its side, so the ten read as a ranking.
 */
export function Movers() {
  const gainers = useStockList(1, 5, undefined, "change_pct", "desc");
  const losers = useStockList(1, 5, undefined, "change_pct", "asc");

  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-16 md:px-6 md:py-20">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="label-caps mb-1.5">Across the whole universe</p>
            <h2 className="font-display text-2xl font-semibold tracking-[-0.01em] md:text-[26px]">
              Who moved today
            </h2>
          </div>
          <Link
            to="/markets"
            className="text-sm text-cobalt underline-offset-4 hover:underline dark:text-cobalt-strong"
          >
            Open the markets dashboard
          </Link>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <Side title="Largest gains" query={gainers} tone="up" />
          <Side title="Largest falls" query={losers} tone="down" />
        </div>
      </div>
    </section>
  );
}

function Side({
  title,
  query,
  tone,
}: {
  title: string;
  query: ReturnType<typeof useStockList>;
  tone: "up" | "down";
}) {
  const items = (query.data?.items ?? []).filter((s) => s.change_pct != null);
  const max = Math.max(0.01, ...items.map((s) => Math.abs(s.change_pct ?? 0)));
  return (
    <div className="border border-line bg-surface">
      <p className="label-caps border-b border-line px-5 py-3">{title}</p>
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={Boolean(query.data) && items.length === 0}
        emptyTitle="No moves stored yet"
        emptyMessage="Today's closes have not been stored yet."
        compact
      >
        <ol>
          {items.map((s, i) => (
            <Row key={s.symbol} s={s} rank={i + 1} share={Math.abs(s.change_pct ?? 0) / max} tone={tone} />
          ))}
        </ol>
      </DataState>
    </div>
  );
}

function Row({
  s,
  rank,
  share,
  tone,
}: {
  s: StockSummary;
  rank: number;
  share: number;
  tone: "up" | "down";
}) {
  const bare = s.symbol.replace(".NS", "");
  return (
    <li className="relative border-b border-line last:border-b-0">
      <Link
        to={`/stocks/${encodeURIComponent(bare)}`}
        className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-surface-2/60"
      >
        <span className="num w-4 text-xs text-faint">{rank}</span>
        <StockLogo symbol={s.symbol} name={s.name} size="sm" />
        <span className="min-w-0 flex-1">
          <span className="tkr block text-sm font-semibold">{bare}</span>
          <span className="block truncate text-xs text-muted">{s.name}</span>
        </span>
        <span className="num text-right text-sm">
          <span className="block text-muted">{fmtPrice(s.last_price)}</span>
          <span className={cn("block font-semibold", tone === "up" ? "text-up" : "text-down")}>
            {fmtSignedPct(s.change_pct)}
          </span>
        </span>
      </Link>
      <span
        aria-hidden
        className="absolute bottom-0 left-0 h-0.5"
        style={{
          width: `${Math.round(share * 100)}%`,
          background: tone === "up" ? "var(--up)" : "var(--down)",
          opacity: 0.7,
        }}
      />
    </li>
  );
}
