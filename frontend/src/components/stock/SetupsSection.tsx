import { useSetups } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { CollapsibleSection } from "@/components/stock/CollapsibleSection";
import { fmtDate } from "@/lib/format";
import type { SetupSpread, SetupsResponse } from "@/lib/types";

/**
 * SetupsSection ("stocks like this, what came next"). The weekly pass finds
 * the 200 past month-ends, across about ten years and the whole list, when a
 * share's Strength, Steadiness and distance from its one-year high ranked
 * most like this share's today, and records what its price did over the next
 * 3 and 12 months. Shown as a range against every past month-end, so the
 * reader sees both the spread and whether this setup differs from any other.
 */

const LABEL: Record<string, string> = { "3m": "Next 3 months", "12m": "Next 12 months" };

function signed(v: number | null | undefined, digits = 1): string {
  if (v == null) return "-";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

export function setupsSummary(s: SetupsResponse | undefined): string | null {
  if (!s || s.status !== "ok") return null;
  const y = s.horizons.find((h) => h.horizon === "12m");
  if (!y || !y.similar.n) return null;
  return `In ${y.similar.n} similar past setups, the median 12-month move was ${signed(y.similar.median)}`;
}

function todayText(s: SetupsResponse): string {
  const t = s.today!;
  const below = Math.abs(t.from_high_pct);
  const high = below < 0.5 ? "at its one-year high" : `${below.toFixed(1)}% below its one-year high`;
  return `Strength ${t.strength.toFixed(0)}, Steadiness ${t.steadiness.toFixed(0)}, ${high}`;
}

/** Where a value sits on the shared scale, in percent of the bar's width. */
function scale(lo: number, hi: number) {
  return (v: number) => ((v - lo) / (hi - lo)) * 100;
}

function RangeBar({
  spread,
  at,
  strong,
}: {
  spread: SetupSpread;
  at: (v: number) => number;
  strong: boolean;
}) {
  if (!spread.n || spread.p10 == null || spread.p90 == null) return null;
  const tone = strong ? "bg-cobalt" : "bg-faint";
  return (
    <div className="relative h-5">
      <div
        className={`absolute top-1/2 h-px -translate-y-1/2 ${tone}`}
        style={{ left: `${at(spread.p10)}%`, width: `${at(spread.p90) - at(spread.p10)}%` }}
      />
      <div
        className={`absolute top-1/2 h-2.5 -translate-y-1/2 ${tone} ${strong ? "" : "opacity-60"}`}
        style={{ left: `${at(spread.p25!)}%`, width: `${at(spread.p75!) - at(spread.p25!)}%` }}
      />
      <div
        className="absolute top-0 h-5 w-0.5 bg-foreground"
        style={{ left: `${at(spread.median!)}%` }}
        aria-hidden
      />
    </div>
  );
}

function Horizon({ h }: { h: SetupsResponse["horizons"][number] }) {
  const s = h.similar;
  const a = h.all_samples;
  if (!s.n) {
    return (
      <div className="bg-surface p-5">
        <p className="label-caps">{LABEL[h.horizon]}</p>
        <p className="mt-2 text-sm text-muted">No completed past cases yet.</p>
      </div>
    );
  }
  const values = [s.p10, s.p90, a.p10, a.p90, 0].filter((v): v is number => v != null);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const at = scale(lo - (hi - lo) * 0.04, hi + (hi - lo) * 0.04);
  return (
    <div className="bg-surface p-5">
      <p className="label-caps">{LABEL[h.horizon]}</p>
      <p className="num mt-1.5 text-2xl font-medium">{signed(s.median)}</p>
      <p className="mt-1 text-xs text-muted">
        median of {s.n} similar cases, against {signed(a.median)} for every past month-end
      </p>

      <div className="relative mt-5 space-y-2">
        <div
          className="absolute inset-y-0 w-px bg-line"
          style={{ left: `${at(0)}%` }}
          aria-hidden
        />
        <div className="flex items-center gap-3">
          <span className="w-20 shrink-0 text-[11px] text-muted">Like today</span>
          <div className="relative min-w-0 flex-1">
            <RangeBar spread={s} at={at} strong />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="w-20 shrink-0 text-[11px] text-muted">Any month</span>
          <div className="relative min-w-0 flex-1">
            <RangeBar spread={a} at={at} strong={false} />
          </div>
        </div>
      </div>
      <p className="num mt-2 text-[11px] text-faint">
        Middle half: {signed(s.p25)} to {signed(s.p75)}. Thin line: 8 in 10 cases, {signed(s.p10)}{" "}
        to {signed(s.p90)}.
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div>
          <dt className="text-muted">Price went up</dt>
          <dd className="num mt-0.5 font-medium">
            {s.share_up?.toFixed(0)}% <span className="font-normal text-faint">(any month {a.share_up?.toFixed(0)}%)</span>
          </dd>
        </div>
        <div>
          <dt className="text-muted">Beat the average share</dt>
          <dd className="num mt-0.5 font-medium">
            {s.share_beat_list?.toFixed(0)}% <span className="font-normal text-faint">(half, by definition)</span>
          </dd>
        </div>
      </dl>
    </div>
  );
}

export function SetupsSection({ symbol }: { symbol: string }) {
  const query = useSetups(symbol);
  const s = query.data;

  return (
    <CollapsibleSection
      id="setups"
      kicker="Past patterns"
      title="Stocks like this: what came next"
      summary={setupsSummary(s)}
    >
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        insufficient={s?.status === "none" || undefined}
        insufficientTitle="Not worked out for this share yet"
        insufficientMessage="Similar setups are rebuilt once a week, for shares with at least a year of prices. Nothing is estimated."
      >
        {s && s.status === "ok" && s.today && (
          <>
            <p className="max-w-3xl text-base leading-relaxed">
              Today: <span className="font-medium">{todayText(s)}</span>. These are the{" "}
              {s.neighbours} moments since {fmtDate(s.sample_from)}, across{" "}
              {s.shares?.toLocaleString("en-IN")} shares, when a share looked most like this on
              those three measures, and what its price did next.
            </p>

            <div className="mt-6 grid gap-px border border-line bg-line @3xl:grid-cols-2">
              {s.horizons.map((h) => (
                <Horizon key={h.horizon} h={h} />
              ))}
            </div>

            <p className="mt-4 max-w-3xl text-xs leading-relaxed text-faint">
              Each case is one share at one month-end, measured from the next day's close; this
              share's own past year is left out. The list is today's largest companies, so shares
              that shrank or delisted are missing and every figure is flattered a little, the
              average share's too. Rebuilt weekly (as of {fmtDate(s.asof)}). A description of the
              past, not a forecast.
            </p>
          </>
        )}
      </DataState>
    </CollapsibleSection>
  );
}
