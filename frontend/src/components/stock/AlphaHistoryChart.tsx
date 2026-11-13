import * as React from "react";

import { useAlphaHistory } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { TimeSeriesChart, type TimeSeriesLine } from "@/components/chart/TimeSeriesChart";
import { fmtDate } from "@/lib/format";

/**
 * AlphaHistoryChart: stored Alpha Score snapshots over time (Part D), read
 * from the backend's /alpha/history endpoint. The composite is the primary
 * line, with its price pillar (Strength, methodology v2.0) beside it. The
 * Alpha line starts where a Strength rank exists (about a year after the
 * first stored price). Gaps in the history break
 * the line rather than being interpolated. Sparse history (fewer than two points) is an honest
 * insufficient state: history builds up as scores are computed per day.
 */
export function AlphaHistoryChart({ symbol }: { symbol: string }) {
  const query = useAlphaHistory(symbol);
  const items = query.data?.items ?? [];

  const lines = React.useMemo<TimeSeriesLine[]>(() => {
    if (items.length === 0) return [];
    const series = (
      key: string,
      label: string,
      color: string,
      pick: (i: (typeof items)[number]) => number | null,
    ): TimeSeriesLine => ({
      key,
      label,
      color,
      data: items.map((i) => ({ time: i.date, value: pick(i) })),
    });
    return [
      series("composite", "Alpha", "--cobalt", (i) => i.composite),
      // Only the price pillar is charted beside the composite. The
      // fundamental and sentiment scores exist only on the few live
      // snapshots, so their lines were a few dots at the right edge.
      ...(items.some((i) => i.strength != null)
        ? [series("strength", "Strength", "--accent-coral", (i) => i.strength ?? null)]
        : []),
    ];
  }, [items]);

  const first = items[0]?.date;
  const last = items.at(-1)?.date;

  return (
    <div className="glass rounded-sm p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <p className="label-caps">Alpha over time</p>
        {first && last && (
          <p className="num text-xs text-faint">
            {fmtDate(first)} to {fmtDate(last)}
          </p>
        )}
      </div>
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        insufficient={Boolean(query.data?.insufficient_data) || items.length < 2}
        insufficientTitle="Not enough history yet"
        insufficientMessage="The alpha history chart needs at least two computed snapshots. Scores are computed daily for every stock in the catalog, so the chart fills in automatically."
        compact
      >
        {lines.length > 0 && (
          <>
            <TimeSeriesChart
              lines={lines}
              height={220}
              valueFormatter={(v) => String(Math.round(v))}
            />
            <p className="num mt-2 text-xs text-faint">Scale 0 to 100</p>
          </>
        )}
      </DataState>
    </div>
  );
}
