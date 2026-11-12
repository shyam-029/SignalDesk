import * as React from "react";

import {
  useFundamentals,
  useValuation,
  VALUATION_METRICS,
} from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { CollapsibleSection } from "@/components/stock/CollapsibleSection";
import { PeersTable } from "@/components/stock/PeersTable";
import { ValuationHistory } from "@/components/stock/ValuationHistory";
import { ExplainAction } from "@/components/explain/ExplainAction";
import { InfoDot } from "@/components/data/InfoDot";
import { fmtCompact, fmtRatio } from "@/lib/format";
import { valuationSemantics } from "@/lib/semantic";
import { valuationSummary } from "@/lib/summaries";
import { cn } from "@/lib/utils";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const METRIC_LABELS: Record<string, string> = {
  PE: "P/E",
  EV_EBITDA: "EV/EBITDA",
  PB: "P/B",
  PS: "P/S",
};

const METRIC_INFO_KEYS: Record<string, "pe" | "ev_ebitda" | "pb" | "ps"> = {
  PE: "pe",
  EV_EBITDA: "ev_ebitda",
  PB: "pb",
  PS: "ps",
};

type MetricKeyV = (typeof VALUATION_METRICS)[number];

/**
 * ValuationSection: relative multiples vs same-industry peers.
 *
 * All four multiples are fetched here, once, so the section can decide what
 * to show from the full picture:
 *   - the verdict panel opens on the first multiple that IS computable (a
 *     stock with no P/E but a valid P/B opens on P/B, not on an empty panel);
 *   - a multiple the snapshot cannot produce shows "-" and is not selectable;
 *   - the frame and the grid always render, so a gap in one multiple never
 *     hides the others.
 */
export function ValuationSection({ symbol }: { symbol: string }) {
  const pe = useValuation(symbol, "PE");
  const evEbitda = useValuation(symbol, "EV_EBITDA");
  const pb = useValuation(symbol, "PB");
  const ps = useValuation(symbol, "PS");
  const queries: Record<MetricKeyV, typeof pe> = { PE: pe, EV_EBITDA: evEbitda, PB: pb, PS: ps };
  const fundamentals = useFundamentals(symbol);

  // The user's explicit choice; null until they pick one. Reset per stock.
  const [picked, setPicked] = React.useState<MetricKeyV | null>(null);
  React.useEffect(() => setPicked(null), [symbol]);

  const firstComputable = VALUATION_METRICS.find((m) => queries[m].data) ?? null;
  const metric: MetricKeyV =
    picked && queries[picked].data ? picked : (firstComputable ?? picked ?? "PE");
  const selected = queries[metric];
  const valuation = selected.data;

  const anyLoading = VALUATION_METRICS.some((m) => queries[m].isLoading);
  const error = queryError(selected.error);
  const noPeers = error?.code === "NO_PEERS";
  // Soft codes are data gaps, reported as a note. Only genuine failures
  // (network, 5xx) on every multiple surface as an error.
  const hardErrors = VALUATION_METRICS.map((m) => queries[m].error).filter(
    (e) => e && !isSoft(e),
  ) as Error[];
  const hardError =
    !firstComputable && !anyLoading && hardErrors.length === VALUATION_METRICS.length
      ? hardErrors[0]
      : null;

  const sem = valuation ? valuationSemantics(valuation.status) : null;
  const ratios = fundamentals.data?.key_ratios ?? {};

  return (
    <CollapsibleSection
      id="valuation"
      kicker="Valuation"
      title="Relative valuation"
      summary={valuationSummary(valuation)}
      defaultOpen
      aside={
        <Tabs value={metric} onValueChange={(v) => setPicked(v as MetricKeyV)}>
          <TabsList aria-label="Valuation metric">
            {VALUATION_METRICS.map((m) => (
              <TabsTrigger key={m} value={m} disabled={!queries[m].data}>
                {METRIC_LABELS[m]}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      }
    >
        <DataState
          loading={!firstComputable && anyLoading}
          error={hardError}
          onRetry={() => VALUATION_METRICS.forEach((m) => queries[m].refetch())}
          skeleton={<VerdictSkeleton />}
        >
          <div className="grid gap-8 lg:grid-cols-12">
            {/* Verdict + relative position for the selected multiple. */}
            <div className="lg:col-span-5">
              {valuation ? (
                <div className="border border-line bg-surface p-5">
                  <p className="label-caps">Verdict · {valuation.metric}</p>
                  <p className={cn("mt-1 font-display text-2xl font-semibold", sem?.band.text)}>
                    {sem?.headline}
                  </p>
                  <p className="num mt-1 text-sm text-muted">
                    {valuation.metric} {valuation.current} vs peer median{" "}
                    {valuation.peer_median}
                  </p>
                  <div className="mt-5">
                    <p className="label-caps mb-3">
                      {valuation.symbol.replace(".NS", "")} vs same-industry peers
                    </p>
                    <RelativePosition
                      current={valuation.current}
                      median={valuation.peer_median}
                    />
                    <p className="mt-3 flex justify-between text-xs font-medium text-faint">
                      <span>Cheaper</span>
                      <span>Pricier</span>
                    </p>
                  </div>
                  <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-muted">
                    Margin vs peer median:{" "}
                    <span className={cn("num font-medium", sem?.band.text)}>
                      {fmtSignedShort(valuation.margin_pct)}
                    </span>
                    , trading {valuation.margin_pct < 0 ? "below" : "above"} the peer median.
                  </p>
                </div>
              ) : (
                <div className="border border-dashed border-rule px-5 py-6">
                  <p className="label-caps">Verdict</p>
                  <p className="num mt-1 text-2xl font-medium text-faint">-</p>
                  <p className="mt-2 text-xs leading-relaxed text-muted">
                    {noPeers
                      ? "No valid peer multiples exist for this stock's industry, so a relative verdict would be misleading."
                      : "None of the four multiples can be computed from the stored snapshot (for example negative earnings or a missing EBITDA). Nothing is estimated."}
                  </p>
                </div>
              )}
              <p className="mt-3 text-xs leading-relaxed text-faint">
                &ldquo;Relatively cheaper&rdquo; does not mean intrinsically cheap.
                {valuation
                  ? ` Compared with ${valuation.peers.length} same-industry companies.`
                  : ""}
              </p>
            </div>

            {/* The four multiples. Always rendered: a gap shows "-" and is
                not selectable; the rest stay usable. */}
            <div className="lg:col-span-7">
              <div className="border border-line bg-surface">
                <div className="border-b border-line px-5 py-3">
                  <p className="label-caps">All multiples · stock vs peer median</p>
                </div>
                <div className="grid sm:grid-cols-2">
                  {VALUATION_METRICS.map((m) => (
                    <MultipleRow
                      key={m}
                      metric={m}
                      value={queries[m].data ?? null}
                      loading={queries[m].isLoading}
                      active={m === metric && Boolean(queries[m].data)}
                      onSelect={() => setPicked(m)}
                    />
                  ))}
                </div>

                {/* Secondary inputs, expandable, not the primary focus. */}
                <details className="px-5 py-3">
                  <summary className="flex cursor-pointer items-center justify-between text-xs font-medium text-muted">
                    Valuation inputs
                    <InfoDot metric="value_signal" className="size-3.5" />
                  </summary>
                  <div className="num mt-3 grid grid-cols-3 gap-4 text-xs">
                    <div>
                      <p className="flex items-center gap-1 text-faint">
                        Enterprise Value <InfoDot metric="ev" className="size-3" />
                      </p>
                      <p className="mt-0.5 font-medium">
                        {ratios.enterprise_value != null
                          ? `₹${fmtCompact(ratios.enterprise_value)}`
                          : "-"}
                      </p>
                    </div>
                    <div>
                      <p className="flex items-center gap-1 text-faint">
                        EBITDA <InfoDot metric="ebitda" className="size-3" />
                      </p>
                      <p className="mt-0.5 font-medium">
                        {ratios.ebitda != null ? `₹${fmtCompact(ratios.ebitda)}` : "-"}
                      </p>
                    </div>
                    <div>
                      <p className="flex items-center gap-1 text-faint">
                        Market cap <InfoDot metric="market_cap" className="size-3" />
                      </p>
                      <p className="mt-0.5 font-medium">
                        {ratios.market_cap != null
                          ? `₹${fmtCompact(ratios.market_cap)}`
                          : "-"}
                      </p>
                    </div>
                  </div>
                  <p className="mt-3 text-xs text-faint">
                    Snapshot updated{" "}
                    {fundamentals.data?.updated_at
                      ? new Date(fundamentals.data.updated_at).toLocaleDateString("en-IN")
                      : "-"}
                  </p>
                </details>
              </div>

              <div className="mt-3 flex items-center gap-2">
                <ExplainAction
                  symbol={symbol}
                  questionType="valuation"
                  question="Why is this valued here vs peers?"
                  triggerLabel="Why this valuation?"
                />
              </div>
            </div>
          </div>
        </DataState>

        {/* The same multiples against the stock's own past. */}
        <div className="mt-8">
          <ValuationHistory symbol={symbol} />
        </div>

        {/* Peer comparison table: the same peer set the multiples use. */}
        <div className="mt-8">
          <PeersTable symbol={symbol} />
        </div>
    </CollapsibleSection>
  );
}

function isSoft(error: unknown): boolean {
  const code = (error as { code?: string } | null)?.code;
  return code === "NO_PEERS" || code === "INSUFFICIENT_DATA";
}

function VerdictSkeleton() {
  return (
    <div className="grid gap-8 lg:grid-cols-12">
      <div className="lg:col-span-5 space-y-3">
        <div className="h-4 w-28 animate-pulse bg-surface-2" />
        <div className="h-8 w-48 animate-pulse bg-surface-2" />
        <div className="h-4 w-64 animate-pulse bg-surface-2" />
      </div>
      <div className="lg:col-span-7 grid grid-cols-2 gap-px border border-line bg-line">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="bg-surface px-5 py-4">
            <div className="h-3 w-16 animate-pulse bg-surface-2" />
            <div className="mt-2 h-6 w-20 animate-pulse bg-surface-2" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Marker scale: the target's multiple vs the peer median, on a shared axis. */
function RelativePosition({ current, median }: { current: number; median: number }) {
  const lo = Math.min(current, median) * 0.85;
  const hi = Math.max(current, median) * 1.15;
  const pct = (v: number) => ((v - lo) / (hi - lo)) * 100;
  const cheaper = current <= median;

  return (
    <div className="relative h-10">
      <div className="absolute inset-x-0 top-2 h-px bg-rule" />
      <span
        className="absolute top-2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{
          left: `${clamp(pct(current))}%`,
          background: cheaper ? "var(--band-positive)" : "var(--band-weak)",
        }}
      />
      <span
        className="absolute top-2 -translate-x-1/2 -translate-y-1/2"
        style={{ left: `${clamp(pct(median))}%` }}
      >
        <span className="block h-4 w-px bg-cobalt dark:bg-cobalt-strong" />
      </span>
      <span
        className="num absolute top-5 -translate-x-1/2 text-xs text-faint"
        style={{ left: `${clamp(pct(median), 6, 94)}%` }}
      >
        median {median.toFixed(1)}
      </span>
    </div>
  );
}

function clamp(v: number, lo = 2, hi = 98): number {
  return Math.min(hi, Math.max(lo, v));
}

/**
 * One multiple cell. A multiple the snapshot cannot produce renders "-" and
 * is inert (not a button): there is nothing behind it to open.
 */
function MultipleRow({
  metric,
  value,
  loading,
  active,
  onSelect,
}: {
  metric: string;
  value: { current: number; peer_median: number } | null;
  loading: boolean;
  active: boolean;
  onSelect: () => void;
}) {
  const cell = "border-b border-line px-5 py-4 text-left sm:[&:nth-child(odd)]:border-r";
  const label = (
    <p className="flex items-center gap-1.5 text-xs text-muted">
      {METRIC_LABELS[metric]}
      <InfoDot metric={METRIC_INFO_KEYS[metric]} className="size-3.5" />
    </p>
  );

  if (loading) {
    return (
      <div className={cell}>
        {label}
        <div className="mt-2 h-5 w-20 animate-pulse bg-surface-2" />
      </div>
    );
  }

  if (!value) {
    return (
      <div className={cell} title="Not computable from the stored snapshot">
        {label}
        <p className="num mt-1 text-xl font-medium text-faint">-</p>
        <p className="mt-0.5 text-xs text-faint">Not computable</p>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={cn(
        cell,
        "relative transition-colors",
        active ? "bg-surface-2" : "hover:bg-surface-2/60",
      )}
    >
      {active && <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-cobalt" />}
      {label}
      <p className="num mt-1 text-xl font-medium">{fmtRatio(value.current, 2)}</p>
      <p className="num mt-0.5 text-xs text-faint">peer median {fmtRatio(value.peer_median)}</p>
    </button>
  );
}

function queryError(error: unknown): { code?: string; message: string } | null {
  if (!error) return null;
  const e = error as { code?: string; message?: string };
  return { code: e.code, message: e.message ?? "Request failed" };
}

function fmtSignedShort(v: number): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}
