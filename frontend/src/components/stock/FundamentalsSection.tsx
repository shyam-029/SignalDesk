import { motion } from "framer-motion";

import { useAltman, useScores } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { CollapsibleSection } from "@/components/stock/CollapsibleSection";
import { FinancialsHistoryChart } from "@/components/stock/FinancialsHistoryChart";
import { InfoDot } from "@/components/data/InfoDot";
import { ExplainAction } from "@/components/explain/ExplainAction";
import { fundamentalsSummary } from "@/lib/summaries";
import { scoreBand } from "@/lib/semantic";
import { cn } from "@/lib/utils";

/**
 * FundamentalsSection: profitability and solvency, anchored by their scores.
 * Each component shows its raw value AND its threshold score, so "why is the
 * score high/low" is visible without extra clicks. Ratios stay neutral; only
 * the scores carry semantic color. Collapsible since Part D: the collapsed
 * header summarizes the stronger dimension from real score components.
 * The multi-year financial history charts live at the bottom of the section.
 */
export function FundamentalsSection({ symbol }: { symbol: string }) {
  const query = useScores(symbol);
  const scores = query.data;
  const summary = fundamentalsSummary(scores);

  const profitBand = scoreBand(scores?.profitability);
  const solvencyBand = scoreBand(scores?.solvency);

  return (
    <CollapsibleSection
      id="fundamentals"
      index="05"
      kicker="Fundamentals"
      title="Business strength"
      summary={summary}
      className="section-alt"
      defaultOpen
      aside={<ExplainAction symbol={symbol} questionType="fundamental" question="What is driving the fundamental scores?" triggerLabel="What's driving this?" />}
    >

        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          insufficient={(scores?.profitability == null && scores?.solvency == null) || undefined}
          insufficientMessage="No financial snapshot exists for this stock yet, so scores cannot be computed. Nothing is estimated."
        >
          {scores && (
            <div className="grid gap-px border border-line bg-line md:grid-cols-2">
              {/* Profitability */}
              <div className="bg-surface p-5">
                <div className="flex items-baseline justify-between">
                  <p className="flex items-center gap-1.5 text-sm font-semibold">
                    Profitability
                    <InfoDot metric="profitability" className="size-3.5" />
                  </p>
                  <p className={cn("num text-2xl font-medium", profitBand?.text)}>
                    {scores.profitability ?? "-"}
                    <span className="ml-1 text-xs text-faint">/100</span>
                  </p>
                </div>
                <div className="mt-2 h-1.5 bg-line">
                  <motion.div
                    className={cn("h-full", profitBand?.bar ?? "bg-faint")}
                    initial={{ width: 0 }}
                    whileInView={{ width: `${scores.profitability ?? 0}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                  />
                </div>
                <div className="mt-4 divide-y divide-line">
                  {scores.profitability_components.map((c) => (
                    <ScoredRatioRow key={c.name} name={c.name} value={c.value} score={c.score} />
                  ))}
                  {scores.profitability_components.length === 0 && (
                    <p className="py-3 text-xs text-faint">
                      Metrics are being refreshed by ingestion; this panel fills in on the next run.
                    </p>
                  )}
                </div>
              </div>

              {/* Solvency */}
              <div className="bg-surface p-5">
                <div className="flex items-baseline justify-between">
                  <p className="flex items-center gap-1.5 text-sm font-semibold">
                    Solvency
                    <InfoDot metric="solvency" className="size-3.5" />
                  </p>
                  <p className={cn("num text-2xl font-medium", solvencyBand?.text)}>
                    {scores.solvency ?? "-"}
                    <span className="ml-1 text-xs text-faint">/100</span>
                  </p>
                </div>
                <div className="mt-2 h-1.5 bg-line">
                  <motion.div
                    className={cn("h-full", solvencyBand?.bar ?? "bg-faint")}
                    initial={{ width: 0 }}
                    whileInView={{ width: `${scores.solvency ?? 0}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                  />
                </div>
                <div className="mt-4 divide-y divide-line">
                  {scores.solvency_components.map((c) => (
                    <ScoredRatioRow key={c.name} name={c.name} value={c.value} score={c.score} />
                  ))}
                  {scores.solvency_components.length === 0 && (
                    <p className="py-3 text-xs text-faint">
                      Metrics are being refreshed by ingestion; this panel fills in on the next run.
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}
        </DataState>

        {scores && (
          <p className="mt-4 text-xs leading-relaxed text-muted">{scores.explanation}</p>
        )}

        {/* Altman Z-Score: separate distress diagnostic, never blended into
            the scores above or into Alpha. Own query, own honest states. */}
        <div className="mt-8">
          <AltmanBlock symbol={symbol} />
        </div>

        {/* Multi-year income-statement history (Part D, backend data only). */}
        <div className="mt-8">
          <FinancialsHistoryChart symbol={symbol} />
        </div>
    </CollapsibleSection>
  );
}

function ScoredRatioRow({
  name,
  value,
  score,
}: {
  name: string;
  value: number;
  score: number;
}) {
  const band = scoreBand(score);
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="text-xs font-medium text-muted">{name}</span>
      <span className="flex items-center gap-3">
        <span className="num text-xs font-medium">{formatComponentValue(name, value)}</span>
        <span className="flex items-center gap-1.5">
          <span className="hidden h-1 w-16 bg-line sm:block">
            <span
              className={cn("block h-full", band?.bar)}
              style={{ width: `${score}%` }}
            />
          </span>
          <span className="num w-7 text-right text-xs text-faint">
            {score.toFixed(0)}
          </span>
        </span>
      </span>
    </div>
  );
}

/** Component values arrive normalized: % metrics in percent, ratios plain. */
function formatComponentValue(name: string, value: number): string {
  if (name === "Debt/Equity") return `${value.toFixed(2)}%`;
  if (name === "Interest coverage" || name === "Current ratio")
    return `${value.toFixed(2)}x`;
  return `${value.toFixed(1)}%`;
}

const ALTMAN_ZONE_TONE: Record<string, string> = {
  safe: "text-band-positive",
  grey: "text-muted",
  distress: "text-band-weak",
};

const ALTMAN_ZONE_LABEL: Record<string, string> = {
  safe: "Safe zone",
  grey: "Grey zone",
  distress: "Distress zone",
};

/**
 * AltmanBlock: the Z-Score distress diagnostic as its own panel below the
 * profitability/solvency scores. An available score shows the value, zone
 * and formula inputs; an unavailable score shows the stored reason (missing
 * balance-sheet data or non-applicable financial) instead of a guess.
 */
function AltmanBlock({ symbol }: { symbol: string }) {
  const query = useAltman(symbol);
  const altman = query.data;

  return (
    <div className="border border-line bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-3">
        <p className="label-caps flex items-center gap-1.5">
          Financial distress · Altman Z-Score
          <InfoDot metric="altman" className="size-3.5" />
        </p>
        {altman?.zone && (
          <p className={cn("num text-xs font-semibold", ALTMAN_ZONE_TONE[altman.zone])}>
            {ALTMAN_ZONE_LABEL[altman.zone]}
          </p>
        )}
      </div>
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        insufficient={Boolean(altman && altman.status === "unavailable")}
        insufficientTitle={
          altman?.reason === "non_applicable_financial"
            ? "Not applicable to financials"
            : "Z-Score unavailable"
        }
        insufficientMessage={
          altman?.detail ??
          "Balance-sheet inputs are not stored yet, so no score is computed. Nothing is estimated."
        }
        compact
      >
        {altman && altman.status === "available" && altman.score != null && (
          <div className="px-5 py-4">
            <div className="flex items-baseline justify-between gap-3">
              <p className={cn("num text-2xl font-medium", altman.zone && ALTMAN_ZONE_TONE[altman.zone])}>
                {altman.score.toFixed(2)}
              </p>
              <p className="num text-xs text-faint">safe above 2.6 · distress below 1.1</p>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted">{altman.detail}</p>
            <p className="mt-2 text-xs text-faint">
              Separate diagnostic: not part of the Solvency Score or Alpha.
            </p>
          </div>
        )}
      </DataState>
    </div>
  );
}
