import * as React from "react";
import { motion } from "framer-motion";

import {
  useTechnicals,
  useTechnicalsSeries,
} from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { InfoDot } from "@/components/data/InfoDot";
import { ExplainAction } from "@/components/explain/ExplainAction";
import { CollapsibleSection } from "@/components/stock/CollapsibleSection";
import { TimeSeriesChart, type TimeSeriesLine } from "@/components/chart/TimeSeriesChart";
import { technicalsSummary } from "@/lib/summaries";
import { fmtPrice } from "@/lib/format";
import { scoreBand, technicalVerdict } from "@/lib/semantic";
import { cn } from "@/lib/utils";
import type { TechnicalsSeriesItem } from "@/lib/types";

/**
 * TechnicalsSection (collapsible, Part D): the aggregate technical read plus
 * the indicator series from the backend's /technicals/series endpoint. The
 * frontend renders the series; it never recomputes SMA/EMA/RSI/MACD. When
 * collapsed the header shows the verdict summary (e.g. "Bullish · RSI 62.4")
 * only while indicator data supports it.
 */
export function TechnicalsSection({ symbol }: { symbol: string }) {
  const technicals = useTechnicals(symbol);
  // One trading year of series: long windows render as illegible dense
  // lines at research-page size, so the default is 250 bars.
  const series = useTechnicalsSeries(symbol, 250);
  const t = technicals.data;
  const verdict = technicalVerdict(t?.score);
  const summary = technicalsSummary(t);

  const items = series.data?.items ?? [];

  // Consistent, widely contrasting roles across every technical chart:
  // cobalt = close/MACD line, coral = SMA20/signal, jade = EMA12, amber = RSI.
  const priceLines = React.useMemo(
    () =>
      buildSeriesLines(items, (i) => [
        { key: "close", label: "Close", color: "--cobalt", value: i.close },
        { key: "sma20", label: "SMA 20", color: "--accent-coral", value: i.sma20 },
        { key: "ema12", label: "EMA 12", color: "--accent-jade", value: i.ema12 },
      ]),
    [items],
  );
  const rsiLines = React.useMemo(
    () => buildSeriesLines(items, (i) => [{ key: "rsi14", label: "RSI 14", color: "--accent-amber", value: i.rsi14 }]),
    [items],
  );
  const macdLines = React.useMemo(
    () =>
      buildSeriesLines(items, (i) => [
        { key: "macd", label: "MACD", color: "--cobalt", value: i.macd, width: 1 },
        { key: "signal", label: "Signal", color: "--accent-coral", value: i.macd_signal, width: 1 },
        { key: "hist", label: "Histogram", color: "--accent-teal", value: i.macd_histogram, histogram: true },
      ]),
    [items],
  );

  return (
    <CollapsibleSection
      id="technicals"
      index="06"
      kicker="Technicals"
      title="Technical positioning"
      summary={summary}
    >
      <div className="grid gap-8 lg:grid-cols-12">
        {/* Indicator series: three stacked, equal-size charts. */}
        <div className="space-y-6 lg:col-span-8">
          <div className="border border-line bg-surface p-5">
            <p className="label-caps mb-3">Price with SMA 20 / EMA 12</p>
            <DataState
              loading={series.isLoading}
              error={series.error}
              onRetry={series.refetch}
              insufficient={Boolean(series.data?.insufficient_data) || items.length === 0}
              insufficientMessage="The indicator series needs enough stored daily bars to warm up (about 26 for SMA 20 plus MACD). Missing windows stay blank; values are not estimated."
              compact
            >
              {items.length > 0 && (
                <>
                  <TimeSeriesChart lines={priceLines} height={280} valueFormatter={(v) => fmtPrice(v)} />
                  <p className="num mt-2 text-xs text-faint">
                    {items.length} daily bars · indicator values computed by the backend
                  </p>
                </>
              )}
            </DataState>
          </div>

          <div className="border border-line bg-surface p-5">
            <p className="label-caps mb-3">RSI 14</p>
            <DataState
              loading={series.isLoading}
              error={series.error}
              onRetry={series.refetch}
              insufficient={items.length === 0}
              insufficientMessage="Not enough stored history for RSI 14."
              compact
            >
              {items.length > 0 && (
                <TimeSeriesChart lines={rsiLines} height={280} valueFormatter={(v) => v.toFixed(1)} />
              )}
            </DataState>
          </div>

          <div className="border border-line bg-surface p-5">
            <p className="label-caps mb-3">MACD 12/26/9</p>
            <DataState
              loading={series.isLoading}
              error={series.error}
              onRetry={series.refetch}
              insufficient={items.length === 0}
              insufficientMessage="Not enough stored history for MACD."
              compact
            >
              {items.length > 0 && (
                <TimeSeriesChart lines={macdLines} height={280} valueFormatter={(v) => v.toFixed(2)} />
              )}
            </DataState>
          </div>
        </div>

        {/* Aggregate positioning panel */}
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
    </CollapsibleSection>
  );
}

/** Build one TimeSeriesLine per indicator from per-bar backend rows. */
function buildSeriesLines(
  items: TechnicalsSeriesItem[],
  map: (
    i: TechnicalsSeriesItem,
  ) => Array<{ key: string; label: string; color: string; value: number | null; histogram?: boolean; width?: 1 | 2 }>,
): TimeSeriesLine[] {
  if (items.length === 0) return [];
  const meta = map(items[0]);
  const out = new Map<string, Array<{ time: string; value: number | null }>>();
  for (const s of meta) out.set(s.key, []);
  for (const item of items) {
    for (const s of map(item)) {
      out.get(s.key)!.push({ time: item.date, value: s.value });
    }
  }
  return meta.map((s) => ({ ...s, data: out.get(s.key)! }));
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
