import * as React from "react";
import { motion } from "framer-motion";

import {
  usePrices,
  useTechnicals,
  PRICE_RANGES,
  PRICE_RANGE_LABELS,
  type PriceRange,
} from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { SectionHeader } from "@/components/data/SectionHeader";
import { PriceChart } from "@/components/chart/PriceChart";
import { ExplainAction } from "@/components/explain/ExplainAction";
import { InfoDot } from "@/components/data/InfoDot";
import { fmtPrice } from "@/lib/format";
import { scoreBand, technicalVerdict } from "@/lib/semantic";
import { cn } from "@/lib/utils";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

/**
 * PriceTechnicals: the price chart (real Lightweight Charts) beside the
 * aggregate technical read. The verdict word describes TECHNICAL POSITIONING
 * only (never "the stock is bearish"), and always represents the aggregate
 * indicator evidence, not one day's move.
 */
export function PriceTechnicals({ symbol }: { symbol: string }) {
  const [range, setRange] = React.useState<PriceRange>("6mo");
  const prices = usePrices(symbol, range);
  const technicals = useTechnicals(symbol);

  const t = technicals.data;
  const verdict = technicalVerdict(t?.score);

  return (
    <section id="price" className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
        <SectionHeader index="05" kicker="Price & technicals" title="Price history and positioning" />

        <div className="grid gap-8 lg:grid-cols-12">
          {/* Chart */}
          <div className="lg:col-span-8">
            <div className="border border-line bg-surface p-5">
              <div className="mb-3 flex items-center justify-between">
                <p className="label-caps">Daily closes · OHLC</p>
                <Tabs value={range} onValueChange={(v) => setRange(v as PriceRange)}>
                  <TabsList>
                    {PRICE_RANGES.map((r) => (
                      <TabsTrigger key={r} value={r}>
                        {PRICE_RANGE_LABELS[r]}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
              </div>
              <DataState
                loading={prices.isLoading}
                error={prices.error}
                onRetry={prices.refetch}
                empty={Boolean(prices.data) && (prices.data?.items.length ?? 0) === 0}
                emptyTitle="No price history"
                emptyMessage="No daily bars are stored for this window yet."
                compact
              >
                {prices.data && prices.data.items.length > 0 && (
                  <>
                    <PriceChart bars={prices.data.items} height={340} />
                    <p className="num mt-2 text-xs text-faint">
                      {prices.data.items.length} daily bars · {range} window · resample 1d
                    </p>
                  </>
                )}
              </DataState>
            </div>
          </div>

          {/* Technical positioning panel */}
          <div className="lg:col-span-4">
            <DataState
              loading={technicals.isLoading}
              error={technicals.error}
              onRetry={technicals.refetch}
              insufficient={Boolean(t?.insufficient_data)}
              insufficientMessage="Not enough price history to compute the indicators. SignalDesk shows no technical read rather than a made-up one."
            >
              {t && (
                <div
                  className={cn(
                    "border bg-surface p-5",
                    verdict ? verdict.band.border : "border-line",
                  )}
                >
                  <p className="label-caps">Technical positioning</p>
                  <div className="mt-1 flex items-baseline justify-between gap-2">
                    <p className={cn("font-display text-2xl font-semibold", verdict?.band.text)}>
                      {verdict?.word ?? "-"}
                    </p>
                    <p className={cn("num text-sm font-medium", verdict?.band.text)}>
                      {t.score ?? "-"} / 100
                    </p>
                  </div>
                  <p className="mt-1 text-xs text-faint">
                    Aggregate indicator evidence. Describes the technical picture only.
                  </p>

                  {/* Sub-scores */}
                  <div className="mt-4 space-y-2.5">
                    <SubScore label="Trend" metric="trend" value={t.components.trend} />
                    <SubScore label="Momentum" metric="momentum" value={t.components.momentum} />
                    <SubScore label="Mean reversion" metric="reversion" value={t.components.reversion} />
                  </div>

                  <div className="mt-4 divide-y divide-line border-t border-line">
                    <IndicatorRow
                      metric="sma20"
                      label="SMA 20"
                      reading={fmtPrice(t.sma20)}
                      interpretation={
                        t.sma20 != null && t.last_close != null
                          ? t.last_close >= t.sma20
                            ? "Price above"
                            : "Price below"
                          : "n/a"
                      }
                      positive={t.sma20 != null && t.last_close != null && t.last_close >= t.sma20}
                    />
                    <IndicatorRow
                      metric="ema12"
                      label="EMA 12"
                      reading={fmtPrice(t.ema12)}
                      interpretation={
                        t.ema12 != null && t.last_close != null
                          ? t.last_close >= t.ema12
                            ? "Price above"
                            : "Price below"
                          : "n/a"
                      }
                      positive={t.ema12 != null && t.last_close != null && t.last_close >= t.ema12}
                    />
                    <IndicatorRow
                      metric="rsi14"
                      label="RSI 14"
                      reading={t.rsi14 != null ? t.rsi14.toFixed(1) : "-"}
                      interpretation={rsiWord(t.rsi14)}
                      positive={t.rsi14 == null ? null : t.rsi14 > 50 ? true : t.rsi14 < 30 ? null : false}
                    />
                    <IndicatorRow
                      metric="macd"
                      label="MACD"
                      reading={
                        t.macd.histogram != null
                          ? `${t.macd.histogram > 0 ? "+" : ""}${t.macd.histogram.toFixed(2)}`
                          : "-"
                      }
                      interpretation={
                        t.macd.histogram == null
                          ? "n/a"
                          : t.macd.histogram > 0
                            ? "Positive · bullish momentum"
                            : "Negative · bearish momentum"
                      }
                      positive={t.macd.histogram == null ? null : t.macd.histogram > 0}
                    />
                  </div>

                  <div className="mt-4 flex items-center justify-between gap-2 border-t border-line pt-3">
                    <p className="text-xs leading-relaxed text-faint">
                      Heuristic read of {t.closes_used} daily closes, not a predictive model.
                    </p>
                    <ExplainAction
                      symbol={symbol}
                      questionType="technical"
                      question="Why is the technical score what it is?"
                      triggerLabel="Why?"
                    />
                  </div>
                </div>
              )}
            </DataState>
          </div>
        </div>
      </div>
    </section>
  );
}

function SubScore({
  label,
  metric,
  value,
}: {
  label: string;
  metric: "trend" | "momentum" | "reversion";
  value: number | null;
}) {
  const band = scoreBand(value);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="flex items-center gap-1.5 text-xs font-medium text-muted">
          {label}
          <InfoDot metric={metric} className="size-3" />
        </span>
        <span className={cn("num text-xs font-medium", band?.text)}>
          {value != null ? value.toFixed(0) : "-"}
        </span>
      </div>
      <div className="mt-1 h-1 bg-line">
        <motion.div
          className={cn("h-full", band?.bar ?? "bg-faint")}
          initial={{ width: 0 }}
          animate={{ width: `${value ?? 0}%` }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
    </div>
  );
}

function IndicatorRow({
  metric,
  label,
  reading,
  interpretation,
  positive,
}: {
  metric: "sma20" | "ema12" | "rsi14" | "macd";
  label: string;
  reading: string;
  interpretation: string;
  positive: boolean | null;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <span className="flex items-center gap-1.5 text-xs text-muted">
        {label}
        <InfoDot metric={metric} className="size-3.5" />
      </span>
      <span className="flex items-baseline gap-3">
        <span className="num text-xs font-medium">{reading}</span>
        <span
          className={cn(
            "text-xs font-medium",
            positive == null ? "text-faint" : positive ? "text-band-positive" : "text-band-weak",
          )}
        >
          {interpretation}
        </span>
      </span>
    </div>
  );
}

function rsiWord(rsi: number | null): string {
  if (rsi == null) return "n/a";
  if (rsi >= 70) return "Overbought";
  if (rsi >= 55) return "Strong";
  if (rsi > 30) return rsi > 45 ? "Softening" : "Weak";
  return "Oversold";
}
