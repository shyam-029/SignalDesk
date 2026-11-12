import { ChevronDown } from "lucide-react";

import { useAlpha, useAlphaExplanation, useCompanyProfile } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { ScaleBar, ScoreBlock } from "@/components/data/ScoreBlock";
import { SectionHeader } from "@/components/data/SectionHeader";
import { InfoDot } from "@/components/data/InfoDot";
import { ExplainAction } from "@/components/explain/ExplainAction";
import { AlphaHistoryChart } from "@/components/stock/AlphaHistoryChart";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtSignedPct } from "@/lib/format";
import { scoreBand, valuationSemantics } from "@/lib/semantic";
import { cn } from "@/lib/utils";

/**
 * AlphaSection: the page's major analytical moment.
 * The composite anchors the section; its three weighted components sit beside
 * it and the written explanation reads as a research conclusion. Valuation is
 * shown only as the separate value signal, never visually blended into Alpha.
 *
 * Part I split: the score renders the moment /alpha returns (pure DB math);
 * the written narrative is fetched in parallel from /alpha/explanation and
 * rendered in its own region — only the sentence shows a loading state, and
 * the provider-sourced company background ("About the company") sits below.
 */
export function AlphaSection({ symbol }: { symbol: string }) {
  const query = useAlpha(symbol);
  const alpha = query.data;
  // Enabled only once the score exists: the explanation never blocks it.
  const explanation = useAlphaExplanation(symbol, Boolean(alpha));
  const profile = useCompanyProfile(symbol);

  return (
    <section id="alpha" className="scroll-mt-28 border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-10 md:px-6">
        <SectionHeader kicker="Signal" title="Alpha Score" />

        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          insufficient={Boolean(alpha?.insufficient_data)}
          insufficientMessage="No Alpha composite can be computed. None of the three research dimensions have data for this stock yet."
        >
          {alpha && (
            <div className="grid gap-8 lg:grid-cols-12">
              {/* Score + components */}
              <div className="lg:col-span-7">
                <div className="border border-line bg-surface p-6">
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
                              <span className="text-xs font-medium text-muted">{label}</span>
                              <span className={cn("num text-xs font-medium", b?.text)}>
                                {v != null ? v.toFixed(0) : "-"}
                              </span>
                            </div>
                            <ScaleBar score={v ?? null} band={b} className="mt-1.5" />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Value signal + written explanation */}
              <div className="space-y-6 lg:col-span-5">
                {alpha.value_signal && (
                  <div>
                    <p className="label-caps mb-2">Value signal · separate from Alpha</p>
                    <div className="border border-line bg-surface p-4">
                      <div className="flex items-baseline justify-between gap-2">
                        <p
                          className={cn(
                            "font-display text-lg font-semibold",
                            valuationSemantics(alpha.value_signal.status)?.band.text,
                          )}
                        >
                          {valuationSemantics(alpha.value_signal.status)?.headline ?? "-"}
                        </p>
                        <p className="num text-sm font-medium">
                          {fmtSignedPct(alpha.value_signal.margin_pct)}
                        </p>
                      </div>
                      <p className="num mt-1 text-xs text-muted">
                        {alpha.value_signal.metric} margin vs peer median
                      </p>
                      <p className="mt-2 text-xs leading-relaxed text-faint">
                        {alpha.value_signal.explanation}
                      </p>
                    </div>
                  </div>
                )}

                {/* Written explanation: lazy companion call, own region.
                    Only this sentence shows a loading state (cache misses). */}
                <div className="border border-line bg-surface p-5">
                  <div className="flex items-center justify-between gap-3">
                    <p className="label-caps">Written explanation</p>
                    <ExplainAction
                      symbol={symbol}
                      questionType="alpha"
                      question={`Why is Alpha ${alpha.composite ?? "-"}?`}
                      triggerLabel={`Why is Alpha ${alpha.composite ?? "-"}?`}
                    />
                  </div>
                  <div className="mt-3" aria-live="polite">
                    {explanation.isPending && (
                      <div className="space-y-2">
                        <Skeleton className="h-3.5 w-full" />
                        <Skeleton className="h-3.5 w-11/12" />
                        <Skeleton className="h-3.5 w-2/3" />
                      </div>
                    )}
                    {explanation.isError && (
                      <p className="text-sm leading-relaxed text-faint">
                        The written explanation is unavailable right now.
                      </p>
                    )}
                    {explanation.data && (
                      <>
                        <p className="text-sm leading-relaxed">{explanation.data.explanation}</p>
                        <p className="mt-2 text-xs text-faint">
                          {explanation.data.source === "llm"
                            ? "Written by the configured language model, grounded in the data above."
                            : "Generated deterministically from the data above (language model unavailable)."}
                        </p>
                      </>
                    )}
                  </div>
                  <p className="mt-3 border-t border-line pt-2 text-xs text-faint">
                    Generated from SignalDesk data. Not investment advice.
                  </p>
                </div>
              </div>
            </div>
          )}
        </DataState>

        {/* Score over time: stored snapshots only, never back-filled. */}
        <div className="mt-8">
          <AlphaHistoryChart symbol={symbol} />
        </div>

        {/* Provider-sourced company background, collapsed by default. */}
        <div className="mt-4">
          <CompanyBox
            loading={profile.isLoading}
            error={profile.error ?? null}
            onRetry={profile.refetch}
            summary={profile.data?.business_summary ?? null}
            ceo={profile.data?.ceo ?? null}
            employees={profile.data?.employees ?? null}
            website={profile.data?.website ?? null}
          />
        </div>
      </div>
    </section>
  );
}

const EMPLOYEE_FMT = new Intl.NumberFormat("en-IN");

/**
 * CompanyBox: what the company actually does, in the provider's own words.
 * The summary is stored verbatim from the data provider (never generated);
 * missing fields are omitted rather than invented.
 */
function CompanyBox({
  loading,
  error,
  onRetry,
  summary,
  ceo,
  employees,
  website,
}: {
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
  summary: string | null;
  ceo: string | null;
  employees: number | null;
  website: string | null;
}) {
  return (
    <details className="group border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-3 [&::-webkit-details-marker]:hidden">
        <span className="label-caps">About the company</span>
        <ChevronDown
          aria-hidden
          className="size-4 text-faint transition-transform group-open:rotate-180"
        />
      </summary>
      <div className="border-t border-line">
      <DataState
        loading={loading}
        error={error}
        onRetry={onRetry}
        empty={!summary}
        emptyTitle="No company profile stored"
        emptyMessage="The provider has not supplied a business description for this stock yet. Nothing is generated in the meantime."
        compact
      >
        <div className="px-5 py-4">
          {summary && (
            <div className="space-y-3">
              {summary.split(/\n{2,}|\r\n\r\n/).filter(Boolean).map((para, i) => (
                <p key={i} className="text-sm leading-relaxed text-muted">
                  {para.trim()}
                </p>
              ))}
            </div>
          )}
          {(ceo || employees != null || website) && (
            <div className="num mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t border-line pt-3 text-xs text-muted">
              {ceo && (
                <span>
                  CEO <span className="text-foreground">{ceo}</span>
                </span>
              )}
              {employees != null && (
                <span>
                  Employees <span className="text-foreground">{EMPLOYEE_FMT.format(employees)}</span>
                </span>
              )}
              {website && (
                <span>
                  Website{" "}
                  <a
                    href={website.startsWith("http") ? website : `https://${website}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-foreground underline decoration-line underline-offset-4 hover:text-cobalt dark:hover:text-cobalt-strong"
                  >
                    {website.replace(/^https?:\/\//, "")}
                  </a>
                </span>
              )}
            </div>
          )}
        </div>
      </DataState>
      </div>
    </details>
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
          <span className="num text-xs text-faint">
            {weight != null ? `${Math.round(weight * 100)}%` : ""}
          </span>
        </span>
        <span className={cn("num text-sm font-medium", band?.text)}>{value ?? "-"}</span>
      </div>
      <ScaleBar score={value} band={band} className="mt-1.5" />
    </div>
  );
}
