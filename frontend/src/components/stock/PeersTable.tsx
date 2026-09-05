import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp } from "lucide-react";

import { usePeers } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { StockLogo } from "@/components/stock/StockLogo";
import { fmtPrice, fmtRatio, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * PeersTable: the same-industry peer set the relative valuation uses,
 * served by the backend's /peers endpoint. Each row links to that peer's
 * research page. "-" always means "the snapshot does not carry this metric";
 * a rendered zero is a real zero. No peer cell is ever estimated.
 */
export function PeersTable({ symbol }: { symbol: string }) {
  const query = usePeers(symbol);
  const peers = query.data;

  return (
    <div className="glass rounded-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-3">
        <p className="label-caps">
          Peer comparison
          {peers?.classifier ? ` · ${peers.classifier}` : ""}
        </p>
        <p className="num text-xs text-faint">
          {peers ? `${peers.count} same-industry peer${peers.count === 1 ? "" : "s"}` : ""}
        </p>
      </div>

      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        empty={Boolean(peers) && peers?.count === 0}
        emptyTitle="No classified peers"
        emptyMessage="No other catalog company shares this stock's industry grouping yet, so there is nothing to compare against. The relative valuation endpoints report the same situation."
        compact
      >
        {peers && peers.count > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-left">
              <thead>
                <tr className="border-b border-line">
                  <th scope="col" className="label-caps px-5 py-3">Company</th>
                  <th scope="col" className="label-caps px-3 py-3 text-right">Price</th>
                  <th scope="col" className="label-caps px-3 py-3 text-right">1D</th>
                  <th scope="col" className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-[0.12em] text-cobalt dark:text-cobalt-strong">P/E</th>
                  <th scope="col" className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-[0.12em] text-accent-jade">ROE</th>
                  <th scope="col" className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-[0.12em] text-accent-teal">Net margin</th>
                  <th scope="col" className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-[0.12em] text-accent-coral">D/E</th>
                </tr>
              </thead>
              <tbody>
                {peers.items.map((peer) => (
                  <tr key={peer.symbol} className="border-b border-line last:border-b-0">
                    <td className="px-5 py-3">
                      <Link
                        to={`/stocks/${encodeURIComponent(peer.symbol)}`}
                        className="group flex items-center gap-3"
                      >
                        <StockLogo symbol={peer.symbol} name={peer.name} size="sm" />
                        <span className="min-w-0">
                          <span className="num block text-xs font-semibold text-foreground group-hover:text-cobalt group-hover:underline dark:group-hover:text-cobalt-strong">
                            {peer.symbol}
                          </span>
                          <span className="block max-w-48 truncate text-xs text-muted" title={peer.name}>
                            {peer.name}
                          </span>
                        </span>
                      </Link>
                    </td>
                    <NumCell value={peer.last_price != null ? fmtPrice(peer.last_price) : "-"} />
                    <NumCell
                      value={fmtSignedPct(peer.change_pct)}
                      tone={
                        peer.change_pct == null
                          ? "neutral"
                          : peer.change_pct > 0
                            ? "positive"
                            : peer.change_pct < 0
                              ? "weak"
                              : "neutral"
                      }
                      arrow={
                        peer.change_pct == null || peer.change_pct === 0
                          ? null
                          : peer.change_pct > 0
                      }
                    />
                    <NumCell
                      value={peer.trailing_pe != null ? fmtRatio(peer.trailing_pe) : "-"}
                      title={peer.trailing_pe == null ? "Not in this peer's snapshot" : undefined}
                      tone="cobalt"
                    />
                    <NumCell
                      value={peer.return_on_equity != null ? pctFromDecimal(peer.return_on_equity) : "-"}
                      title={peer.return_on_equity == null ? "Not in this peer's snapshot" : undefined}
                      tone="jade"
                    />
                    <NumCell
                      value={peer.profit_margin != null ? pctFromDecimal(peer.profit_margin) : "-"}
                      title={peer.profit_margin == null ? "Not in this peer's snapshot" : undefined}
                      tone="teal"
                    />
                    <NumCell
                      value={peer.debt_to_equity != null ? pctDirect(peer.debt_to_equity) : "-"}
                      title={peer.debt_to_equity == null ? "Not in this peer's snapshot" : undefined}
                      tone="coral"
                    />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataState>

      <p className="border-t border-line px-5 py-3 text-xs leading-relaxed text-faint">
        &ldquo;-&rdquo; marks a metric this peer&apos;s financial snapshot does not carry; a listed
        zero is a real zero. Ratios come from each peer&apos;s stored snapshot and are never
        estimated.
      </p>
    </div>
  );
}

const TONE_CLASS: Record<string, string> = {
  neutral: "text-foreground",
  positive: "text-band-positive",
  weak: "text-band-weak",
  cobalt: "text-cobalt dark:text-cobalt-strong",
  jade: "text-accent-jade",
  teal: "text-accent-teal",
  coral: "text-accent-coral",
};

function NumCell({
  value,
  tone = "neutral",
  title,
  arrow,
}: {
  value: string;
  tone?: "neutral" | "positive" | "weak" | "cobalt" | "jade" | "teal" | "coral";
  title?: string;
  arrow?: boolean | null;
}) {
  return (
    <td className="px-3 py-3 text-right" title={title}>
      <span
        className={cn(
          "num inline-flex items-center gap-1 text-sm font-semibold",
          TONE_CLASS[tone],
        )}
      >
        {arrow === true && <ArrowUp className="size-3.5" aria-label="up" />}
        {arrow === false && <ArrowDown className="size-3.5" aria-label="down" />}
        {value}
      </span>
    </td>
  );
}

/** Snapshot ROE/margins are decimals (0.154 = 15.4%). */
function pctFromDecimal(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** Snapshot D/E is already in percent units (36.7 = 36.7%). */
function pctDirect(value: number): string {
  return `${value.toFixed(1)}%`;
}
