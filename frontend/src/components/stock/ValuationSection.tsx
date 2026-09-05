import * as React from "react";
import { motion } from "framer-motion";

import {
  useFundamentals,
  useValuation,
  VALUATION_METRICS,
} from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { CollapsibleSection } from "@/components/stock/CollapsibleSection";
import { PeersTable } from "@/components/stock/PeersTable";
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

/**
 * ValuationSection: relative multiples vs same-industry peers.
 * All four supported multiples (P/E, EV/EBITDA, P/B, P/S) are shown, each with
 * its own peer median from the backend (one lightweight query per multiple,
 * cached by TanStack Query). Valuation carries its OWN semantic state and
 * never inherits Alpha's color. EV/EBITDA/market-cap inputs live in a
 * secondary expandable area, not the primary view.
 */
export function ValuationSection({ symbol }: { symbol: string }) {
  const [metric, setMetric] = React.useState<string>("PE");
  const selected = useValuation(symbol, metric as "PE" | "EV_EBITDA" | "PB" | "PS");
  const fundamentals = useFundamentals(symbol);
  const valuation = selected.data;

  const error = queryError(selected.error);
  const noPeers = error?.code === "NO_PEERS";
  const insufficient = error?.code === "INSUFFICIENT_DATA";

  const sem = valuation ? valuationSemantics(valuation.status) : null;
  const ratios = fundamentals.data?.key_ratios ?? {};

  return (
    <CollapsibleSection
      id="valuation"
      index="04"
      kicker="Valuation"
      title="Relative valuation"
      summary={valuationSummary(valuation)}
      defaultOpen
      aside={
        <Tabs value={metric} onValueChange={setMetric}>
          <TabsList aria-label="Valuation metric">
            {VALUATION_METRICS.map((m) => (
              <TabsTrigger key={m} value={m}>
                {METRIC_LABELS[m]}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      }
    >

        <DataState
          loading={selected.isLoading}
          error={selected.error}
          onRetry={selected.refetch}
          insufficient={Boolean(insufficient || noPeers)}
          insufficientTitle={noPeers ? "No comparable peers" : "Not computable"}
          insufficientMessage={
            noPeers
              ? "No valid peer multiples exist for this stock's industry, so a relative valuation would be misleading. SignalDesk refuses to guess."
              : "The stock's financial snapshot lacks the inputs needed for this multiple. Nothing is estimated in the meantime."
          }
        >
          {valuation && (
            <div className="grid gap-8 lg:grid-cols-12">
              {/* Status + relative position for the selected metric */}
              <div className="lg:col-span-5">
                <div
                  className={cn(
                    "border bg-surface p-5",
                    sem?.band.border,
                    sem && `${sem.band.bg.replace("/10", "/6")}`,
                  )}
                >
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
                      {valuation.symbol} vs same-industry peers
                    </p>
                    <RelativePosition
                      current={valuation.current}
                      median={valuation.peer_median}
                    />
                    <p className="mt-3 flex justify-between text-xs font-medium text-faint">
                      <span>Cheapest peer</span>
                      <span>Priciest peer</span>
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
                <p className="mt-3 text-xs leading-relaxed text-faint">
                  &ldquo;Relatively cheaper&rdquo; does not mean intrinsically cheap. Peer set:{" "}
                  {valuation.peers.length} same-industry companies from the SignalDesk catalog.
                </p>
              </div>

              {/* The four multiples, each backed by its own valuation query. */}
              <div className="lg:col-span-7">
                <div className="border border-line bg-surface">
                  <div className="border-b border-line px-5 py-3">
                    <p className="label-caps">All multiples · stock vs peer median</p>
                  </div>
                  <div className="grid sm:grid-cols-2">
                    {VALUATION_METRICS.map((m) => (
                      <MultipleRow
                        key={m}
                        symbol={symbol}
                        metric={m}
                        active={m === metric}
                        onSelect={() => setMetric(m)}
                      />
                    ))}
                  </div>

                  {/* Secondary inputs, expandable, not the primary focus. */}
                  <details className="border-t border-line px-5 py-3">
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
                      Underlying inputs for the multiples above · snapshot updated{" "}
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
          )}
        </DataState>

        {/* Peer comparison table (Part D): the same peer set the multiples use. */}
        <div className="mt-8">
          <PeersTable symbol={symbol} />
        </div>
    </CollapsibleSection>
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
      <motion.span
        className="absolute top-2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{ background: cheaper ? "var(--band-positive)" : "var(--band-weak)" }}
        initial={{ left: "0%" }}
        animate={{ left: `${clamp(pct(current))}%` }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
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
 * One multiple row: owns its valuation query so all four multiples display
 * their own peer medians simultaneously (the endpoint is per-metric).
 */
function MultipleRow({
  symbol,
  metric,
  active,
  onSelect,
}: {
  symbol: string;
  metric: string;
  active: boolean;
  onSelect: () => void;
}) {
  const query = useValuation(symbol, metric);
  const v = query.data;
  const err = queryError(query.error);

  return (
    <button
      onClick={onSelect}
      className={cn(
        "border-b border-line px-5 py-4 text-left transition-colors sm:[&:nth-child(odd)]:border-r",
        active ? "bg-surface-2" : "hover:bg-surface-2/60",
      )}
      aria-pressed={active}
    >
      <p className="flex items-center gap-1.5 text-xs text-muted">
        {METRIC_LABELS[metric]}
        <InfoDot metric={METRIC_INFO_KEYS[metric]} className="size-3.5" />
        {active && err == null && <span className="label-caps ml-1">chart shown</span>}
      </p>
      {err ? (
        <p className="num mt-1 text-xl font-medium text-faint">-</p>
      ) : v ? (
        <>
          <p className="num mt-1 text-xl font-medium">{fmtRatio(v.current, 2)}</p>
          <p className="num mt-0.5 text-xs text-faint">
            peer median {fmtRatio(v.peer_median)}
          </p>
        </>
      ) : (
        <div className="mt-2 h-5 w-20 animate-pulse bg-surface-2" />
      )}
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
