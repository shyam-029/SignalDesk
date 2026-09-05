import { usePeers } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { fmtPrice, fmtRatio, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * PeersTable: the same-industry peer set the relative valuation uses
 * (Part D), served by the backend's /peers endpoint. Rows show the latest
 * price plus valuation/profitability/solvency context from each peer's
 * financials snapshot. "-" always means "the snapshot does not carry this
 * metric"; a rendered zero is a real zero. No peer cell is ever estimated.
 */
export function PeersTable({ symbol }: { symbol: string }) {
  const query = usePeers(symbol);
  const peers = query.data;

  return (
    <div className="border border-line bg-surface">
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
            <table className="w-full min-w-[640px] border-collapse text-left">
              <thead>
                <tr className="border-b border-line">
                  <th scope="col" className="label-caps px-5 py-2.5">Company</th>
                  <th scope="col" className="label-caps px-3 py-2.5 text-right">Price</th>
                  <th scope="col" className="label-caps px-3 py-2.5 text-right">1D</th>
                  <th scope="col" className="label-caps px-3 py-2.5 text-right">P/E</th>
                  <th scope="col" className="label-caps px-3 py-2.5 text-right">ROE</th>
                  <th scope="col" className="label-caps px-3 py-2.5 text-right">Net margin</th>
                  <th scope="col" className="label-caps px-3 py-2.5 text-right">D/E</th>
                </tr>
              </thead>
              <tbody>
                {peers.items.map((peer) => (
                  <tr
                    key={peer.symbol}
                    className="border-b border-line last:border-b-0 hover:bg-surface-2/50"
                  >
                    <td className="px-5 py-3">
                      <p className="num text-xs font-semibold">{peer.symbol}</p>
                      <p className="mt-0.5 max-w-48 truncate text-xs text-muted" title={peer.name}>
                        {peer.name}
                      </p>
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
                    />
                    <NumCell
                      value={peer.trailing_pe != null ? fmtRatio(peer.trailing_pe) : "-"}
                      title={peer.trailing_pe == null ? "Not in this peer's snapshot" : undefined}
                    />
                    <NumCell
                      value={peer.return_on_equity != null ? pctFromDecimal(peer.return_on_equity) : "-"}
                      title={peer.return_on_equity == null ? "Not in this peer's snapshot" : undefined}
                    />
                    <NumCell
                      value={peer.profit_margin != null ? pctFromDecimal(peer.profit_margin) : "-"}
                      title={peer.profit_margin == null ? "Not in this peer's snapshot" : undefined}
                    />
                    <NumCell
                      value={peer.debt_to_equity != null ? pctDirect(peer.debt_to_equity) : "-"}
                      title={peer.debt_to_equity == null ? "Not in this peer's snapshot" : undefined}
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

function NumCell({ value, tone = "neutral", title }: { value: string; tone?: "neutral" | "positive" | "weak"; title?: string }) {
  return (
    <td className="px-3 py-3 text-right" title={title}>
      <span
        className={cn(
          "num text-xs font-medium",
          tone === "positive" ? "text-band-positive" : tone === "weak" ? "text-band-weak" : "text-foreground",
        )}
      >
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
