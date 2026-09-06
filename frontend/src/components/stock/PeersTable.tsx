import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { usePeers } from "@/lib/hooks";
import type { PeerSummary } from "@/lib/types";
import { DataState } from "@/components/data/DataState";
import { StockLogo } from "@/components/stock/StockLogo";
import { fmtPrice, fmtRatio, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * PeersTable: the same-industry peer set the relative valuation uses,
 * served by the backend's /peers endpoint. Each row links to that peer's
 * research page. "-" always means "the snapshot does not carry this metric";
 * a rendered zero is a real zero. No peer cell is ever estimated.
 *
 * Three peers show by default (the closest read: sorted as chosen) and the
 * footer toggle expands to the full set. Every metric column sorts; peers
 * without a metric sort last in both directions.
 */
type SortKey = "symbol" | "price" | "change" | "pe" | "roe" | "netMargin" | "de";
type SortDir = "asc" | "desc";

const COLUMNS: Array<{
  key: SortKey;
  label: string;
  tone?: string;
  numeric?: boolean;
}> = [
  { key: "symbol", label: "Company" },
  { key: "price", label: "Price", numeric: true },
  { key: "change", label: "1D", numeric: true },
  { key: "pe", label: "P/E", tone: "text-cobalt dark:text-cobalt-strong", numeric: true },
  { key: "roe", label: "ROE", tone: "text-accent-jade", numeric: true },
  { key: "netMargin", label: "Net margin", tone: "text-accent-teal", numeric: true },
  { key: "de", label: "D/E", tone: "text-accent-coral", numeric: true },
];

const COLLAPSED_ROWS = 3;

function sortValue(peer: PeerSummary, key: SortKey): number | string | null {
  switch (key) {
    case "symbol":
      return peer.symbol;
    case "price":
      return peer.last_price;
    case "change":
      return peer.change_pct;
    case "pe":
      return peer.trailing_pe;
    case "roe":
      return peer.return_on_equity;
    case "netMargin":
      return peer.profit_margin;
    case "de":
      return peer.debt_to_equity;
  }
}

function sortPeers(items: PeerSummary[], key: SortKey, dir: SortDir): PeerSummary[] {
  return [...items].sort((a, b) => {
    const va = sortValue(a, key);
    const vb = sortValue(b, key);
    // Missing metrics sort last in both directions (never "smallest").
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    let cmp: number;
    if (typeof va === "string" || typeof vb === "string") {
      cmp = String(va).localeCompare(String(vb));
    } else {
      cmp = va - vb;
    }
    return dir === "asc" ? cmp : -cmp;
  });
}

export function PeersTable({ symbol }: { symbol: string }) {
  const query = usePeers(symbol);
  const peers = query.data;

  const [sortKey, setSortKey] = React.useState<SortKey>("symbol");
  const [sortDir, setSortDir] = React.useState<SortDir>("asc");
  const [expanded, setExpanded] = React.useState(false);

  const items = peers?.items ?? [];
  const sorted = React.useMemo(
    () => sortPeers(items, sortKey, sortDir),
    [items, sortKey, sortDir],
  );
  const visible = expanded ? sorted : sorted.slice(0, COLLAPSED_ROWS);
  const collapsible = sorted.length > COLLAPSED_ROWS;

  const onSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

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
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-line">
                    {COLUMNS.map((col) => {
                      const active = sortKey === col.key;
                      return (
                        <th
                          key={col.key}
                          scope="col"
                          aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                          className={cn(
                            "px-3 py-3",
                            col.key === "symbol" && "pl-5",
                            col.numeric ? "text-right" : "text-left",
                          )}
                        >
                          <button
                            type="button"
                            onClick={() => onSort(col.key)}
                            className={cn(
                              "label-caps inline-flex cursor-pointer items-center gap-1 transition-colors hover:text-foreground",
                              active && "text-foreground",
                              col.tone && !active && col.tone,
                            )}
                            title={`Sort by ${col.label}`}
                          >
                            {col.label}
                            {active ? (
                              sortDir === "asc" ? (
                                <ArrowUp className="size-3" aria-hidden />
                              ) : (
                                <ArrowDown className="size-3" aria-hidden />
                              )
                            ) : (
                              <ArrowUpDown className="size-3 opacity-40" aria-hidden />
                            )}
                          </button>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {visible.map((peer) => (
                    <PeerRow key={peer.symbol} peer={peer} />
                  ))}
                </tbody>
              </table>
            </div>

            {collapsible && (
              <div className="border-t border-line px-5 py-2 text-center">
                <button
                  type="button"
                  onClick={() => setExpanded((v) => !v)}
                  aria-expanded={expanded}
                  className="label-caps inline-flex cursor-pointer items-center gap-1.5 text-muted transition-colors hover:text-foreground"
                >
                  {expanded ? (
                    <>
                      Show less
                      <ArrowUp className="size-3" aria-hidden />
                    </>
                  ) : (
                    <>
                      Show all {peers.count} peers
                      <ArrowDown className="size-3" aria-hidden />
                    </>
                  )}
                </button>
              </div>
            )}
          </>
        )}
      </DataState>

      <p className="border-t border-line px-5 py-3 text-xs leading-relaxed text-faint">
        &ldquo;-&rdquo; marks a metric this peer&apos;s financial snapshot does not carry; a listed
        zero is a real zero. Ratios come from each peer&apos;s stored snapshot and are never
        estimated. Click a column to sort; peers missing that metric sort last.
      </p>
    </div>
  );
}

function PeerRow({ peer }: { peer: PeerSummary }) {
  return (
    <tr className="border-b border-line last:border-b-0">
      <td className="py-3 pl-5 pr-3">
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
