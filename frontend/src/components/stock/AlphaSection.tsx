import { motion } from "framer-motion";

import { useAlpha } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { ScoreBlock } from "@/components/data/ScoreBlock";
import { SectionHeader } from "@/components/data/SectionHeader";
import { InfoDot } from "@/components/data/InfoDot";
import { ExplainAction } from "@/components/explain/ExplainAction";
import { fmtSignedPct } from "@/lib/format";
import { scoreBand, valuationSemantics } from "@/lib/semantic";
import { cn } from "@/lib/utils";

/**
 * AlphaSection — the page's major analytical moment.
 * The composite anchors the section; its three weighted components sit beside
 * it and the grounded explanation reads as a research conclusion. Valuation is
 * shown only as the separate value signal — never visually blended into Alpha.
 */
export function AlphaSection({ symbol }: { symbol: string }) {
  const query = useAlpha(symbol);
  const alpha = query.data;

  const compositeBand = scoreBand(alpha?.composite);

  return (
    <section id="alpha" className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
        <SectionHeader
          index="02"
          kicker="Signal"
          title="Alpha Score"
          aside={
            <p className="num text-xs text-muted">
              40% fundamental · 30% technical · 30% sentiment
            </p>
          }
        />

        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          insufficient={Boolean(alpha?.insufficient_data)}
          insufficientMessage="No Alpha composite can be computed — none of the three research dimensions have data for this stock yet."
        >
          {alpha && (
            <div className="grid gap-8 lg:grid-cols-12">
              {/* Score + components */}
              <div className="lg:col-span-7">
                <div
                  className={cn(
                    "border bg-surface p-6 transition-colors",
                    compositeBand?.border,
                    compositeBand && `${compositeBand.bg.replace("/10", "/6")}`,
                  )}
                >
                  <div className="grid gap-6 md:grid-cols-2">
                    <ScoreBlock
                      score={alpha.composite}
                      label="Alpha Score"
                      metric="alpha"
                      size="lg"
                      flat
                    />
                    <div className="space-y-3">
                      <ComponentBar
                        label="Fundamental"
                        value={alpha.fundamental}
                        weight={alpha.weights.fundamental}
                        metric="fundamental_score"
                      />
                      <ComponentBar
                        label="Technical"
                        value={alpha.technical}
                        weight={alpha.weights.technical}
                        metric="technical_score"
                      />
                      <ComponentBar
                        label="Sentiment"
                        value={alpha.sentiment}
                        weight={alpha.weights.sentiment}
                        metric="sentiment_score"
                      />
                    </div>
                  </div>
                </div>

                {/* Technical sub-components (evidence, not conclusions). */}
                {Object.keys(alpha.components).length > 0 && (
                  <div className="mt-4 border border-line bg-surface p-4">
                    <p className="label-caps mb-3">Technical evidence</p>
                    <div className="grid grid-cols-3 gap-4">
                      {[
                        ["trend", "Trend"],
                        ["momentum", "Momentum"],
                        ["reversion", "Mean reversion"],
                      ].map(([key, label]) => {
                        const v = alpha.components[key];
                        const b = scoreBand(v);
                        return (
                          <div key={key}>
                            <div className="flex items-baseline justify-between">
                              <span className="text-[11px] text-muted">{label}</span>
                              <span className={cn("num text-xs font-medium", b?.text)}>
                                {v != null ? v.toFixed(0) : "—"}
                              </span>
                            </div>
                            <div className="mt-1.5 h-1 bg-line">
                              <motion.div
                                className={cn("h-full", b?.bar ?? "bg-faint")}
                                initial={{ width: 0 }}
                                animate={{ width: `${v ?? 0}%` }}
                                transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Value signal + grounded explanation */}
              <div className="space-y-6 lg:col-span-5">
                {alpha.value_signal && (
                  <div>
                    <p className="label-caps mb-2">Value signal · separate from Alpha</p>
                    <div
                      className={cn(
                        "border bg-surface p-4",
                        valuationSemantics(alpha.value_signal.status)?.band.border,
                      )}
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <p
                          className={cn(
                            "font-display text-lg font-semibold",
                            valuationSemantics(alpha.value_signal.status)?.band.text,
                          )}
                        >
                          {valuationSemantics(alpha.value_signal.status)?.headline ?? "—"}
                        </p>
                        <p className="num text-sm font-medium">
                          {fmtSignedPct(alpha.value_signal.margin_pct)}
                        </p>
                      </div>
                      <p className="num mt-1 text-xs text-muted">
                        {alpha.value_signal.metric} margin vs peer median
                      </p>
                      <p className="mt-2 text-[11px] leading-relaxed text-faint">
                        {alpha.value_signal.explanation}
                      </p>
                    </div>
                  </div>
                )}

                <div className="border border-line bg-surface p-5">
                  <div className="flex items-center justify-between gap-3">
                    <p className="label-caps">Grounded explanation</p>
                    <ExplainAction
                      symbol={symbol}
                      questionType="alpha"
                      question={`Why is Alpha ${alpha.composite ?? "—"}?`}
                      triggerLabel={`Why is Alpha ${alpha.composite ?? "—"}?`}
                    />
                  </div>
                  <p className="mt-3 text-sm leading-relaxed">{alpha.explanation}</p>
                  <p className="mt-3 border-t border-line pt-2 text-[10px] text-faint">
                    Generated explanation · grounded in SignalDesk data · not investment advice
                  </p>
                </div>
              </div>
            </div>
          )}
        </DataState>
      </div>
    </section>
  );
}

function ComponentBar({
  label,
  value,
  weight,
  metric,
}: {
  label: string;
  value: number | null;
  weight?: number;
  metric: "fundamental_score" | "technical_score" | "sentiment_score";
}) {
  const band = scoreBand(value);
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs text-muted">
          {label}
          <InfoDot metric={metric} className="size-3.5" />
          <span className="num text-[10px] text-faint">
            {weight != null ? `${Math.round(weight * 100)}%` : ""}
          </span>
        </span>
        <span className={cn("num text-sm font-medium", band?.text)}>{value ?? "—"}</span>
      </div>
      <div className="mt-1 flex gap-[3px]" aria-hidden>
        {Array.from({ length: 20 }, (_, i) => (
          <span
            key={i}
            className={cn(
              "h-1 flex-1",
              i < Math.round(((value ?? 0) / 100) * 20) ? band?.bar ?? "bg-line" : "bg-line",
            )}
          />
        ))}
      </div>
    </div>
  );
}
