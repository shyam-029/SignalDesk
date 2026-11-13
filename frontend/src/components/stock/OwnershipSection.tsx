import { useShareholding } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { InfoDot } from "@/components/data/InfoDot";
import { CollapsibleSection } from "@/components/stock/CollapsibleSection";
import { quarterLabel } from "@/components/stock/QuarterlyTrend";
import type { OwnershipQuarter, ShareholdingResponse } from "@/lib/types";

/**
 * OwnershipSection: who owns the company and whether the informed owners are
 * adding or leaving. Quarterly shareholding filings, read from the backend's
 * /shareholding endpoint. A category that was not reported shows "-" and is
 * never worked out as "100 minus the rest". History starts when the data
 * was first stored, so the comparison window grows over time.
 */

type CategoryKey = "promoters" | "fii" | "other_dii" | "mutual_funds" | "retail_and_other";

const CATEGORIES: Array<{
  key: CategoryKey;
  label: string;
  color: string;
  help: string;
}> = [
  {
    key: "promoters",
    label: "Promoters",
    color: "var(--cobalt)",
    help: "The founders and controlling group. A rising share is usually read as confidence; a falling one deserves a look at why.",
  },
  {
    key: "fii",
    label: "Foreign institutions",
    color: "var(--accent-teal)",
    help: "Overseas funds and investors registered to invest in Indian markets.",
  },
  {
    key: "mutual_funds",
    label: "Mutual funds",
    color: "var(--accent-jade)",
    help: "Indian mutual fund schemes.",
  },
  {
    key: "other_dii",
    label: "Other domestic institutions",
    color: "var(--accent-coral)",
    help: "Indian insurers, banks, pension funds and similar institutions, excluding mutual funds.",
  },
  {
    key: "retail_and_other",
    label: "Public and others",
    color: "var(--faint)",
    help: "Individual investors and every holder not counted in the other groups.",
  },
];

function pct(value: number | null | undefined): string {
  return value == null ? "-" : `${value.toFixed(2)}%`;
}

function pts(value: number | null | undefined): string {
  if (value == null) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)} pts`;
}

const DIRECTION_WORD: Record<string, string> = {
  rising: "rose",
  falling: "fell",
  steady: "was steady",
};

export function ownershipSummary(data: ShareholdingResponse | undefined): string | null {
  const latest = data?.quarters.at(-1);
  if (!data || !latest || latest.promoters == null) return null;
  const parts = [`Promoters ${latest.promoters.toFixed(1)}%`];
  if (latest.institutions != null) parts.push(`institutions ${latest.institutions.toFixed(1)}%`);
  return parts.join(" · ");
}

function headline(data: ShareholdingResponse): string | null {
  if (!data.from_period || !data.to_period) return null;
  const span = `between ${quarterLabel(data.from_period)} and ${quarterLabel(data.to_period)}`;
  const bits: string[] = [];
  if (data.promoter_direction) {
    const change = data.change_pts.promoters;
    bits.push(
      data.promoter_direction === "steady"
        ? "Promoter holding was steady"
        : `Promoter holding ${DIRECTION_WORD[data.promoter_direction]} ${Math.abs(change ?? 0).toFixed(2)} points`,
    );
  }
  if (data.institution_direction) {
    const change = data.change_pts.institutions;
    bits.push(
      data.institution_direction === "steady"
        ? "institutional holding was steady"
        : `institutional holding ${DIRECTION_WORD[data.institution_direction]} ${Math.abs(change ?? 0).toFixed(2)} points`,
    );
  }
  if (bits.length === 0) return null;
  return `${bits.join(" and ")} ${span}.`;
}

export function OwnershipSection({ symbol }: { symbol: string }) {
  const query = useShareholding(symbol);
  const data = query.data;
  const quarters: OwnershipQuarter[] = data ? [...data.quarters].reverse() : [];
  const latest = quarters[0];
  const line = data ? headline(data) : null;

  return (
    <CollapsibleSection
      id="ownership"
      kicker="Ownership"
      title="Who owns it"
      summary={ownershipSummary(data)}
      defaultOpen
    >
      <DataState
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        insufficient={data?.insufficient_data || undefined}
        insufficientTitle="No shareholding filings stored yet"
        insufficientMessage="The ownership pattern is collected a batch of companies at a time and appears here once this company has been reached. Nothing is estimated."
      >
        {data && latest && (
          <div className="grid gap-8 @4xl:grid-cols-12">
            <div className="@4xl:col-span-5">
              <p className="label-caps">As of {quarterLabel(latest.period_end)}</p>
              {line ? (
                <p className="mt-2 text-sm font-medium leading-relaxed">{line}</p>
              ) : (
                <p className="mt-2 text-xs leading-relaxed text-muted">
                  Only one quarter is stored so far, so there is no change to report yet.
                </p>
              )}

              <div className="mt-5 space-y-2.5">
                {quarters.map((q) => (
                  <div key={q.period_end} className="flex items-center gap-3">
                    <span className="num w-16 shrink-0 text-xs text-muted">
                      {quarterLabel(q.period_end)}
                    </span>
                    <StackBar quarter={q} />
                  </div>
                ))}
              </div>

              <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted">
                {CATEGORIES.map((c) => (
                  <li key={c.key} className="flex items-center gap-1.5">
                    <span className="block size-2" style={{ background: c.color }} />
                    {c.label}
                  </li>
                ))}
              </ul>
            </div>

            <div className="@4xl:col-span-7">
              <div className="overflow-x-auto border border-line bg-surface">
                <table className="num w-full min-w-[520px] text-right text-xs">
                  <thead>
                    <tr className="border-b border-line text-faint">
                      <th className="px-4 py-2.5 text-left font-medium">Holder</th>
                      {quarters.map((q) => (
                        <th key={q.period_end} className="px-3 py-2.5 font-medium">
                          {quarterLabel(q.period_end)}
                        </th>
                      ))}
                      <th className="px-4 py-2.5 font-medium">Change</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {CATEGORIES.map((c) => (
                      <tr key={c.key}>
                        <td className="px-4 py-2.5 text-left">
                          <span className="inline-flex items-center gap-2 font-medium">
                            <span className="block size-2" style={{ background: c.color }} />
                            {c.label}
                            <InfoDot
                              info={{ label: c.label, short: c.help }}
                              glyph="?"
                              className="size-3.5"
                            />
                          </span>
                        </td>
                        {quarters.map((q) => (
                          <td key={q.period_end} className="px-3 py-2.5">
                            {pct(q[c.key])}
                          </td>
                        ))}
                        <td className="px-4 py-2.5 font-medium">{pts(data.change_pts[c.key])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-faint">
                Percent of all shares at each quarter end, from the company&rsquo;s filings.
                Change is from the oldest to the newest quarter shown, in percentage points.
                Promoter pledging is not included.
              </p>
            </div>
          </div>
        )}
      </DataState>
    </CollapsibleSection>
  );
}

/** One quarter as a 100% bar. A category that was not reported leaves a gap. */
function StackBar({ quarter }: { quarter: OwnershipQuarter }) {
  return (
    <span
      className="flex h-3 flex-1 overflow-hidden bg-line"
      role="img"
      aria-label={CATEGORIES.map((c) => `${c.label} ${pct(quarter[c.key])}`).join(", ")}
    >
      {CATEGORIES.map((c) => {
        const value = quarter[c.key];
        if (value == null || value <= 0) return null;
        return (
          <span
            key={c.key}
            title={`${c.label} ${pct(value)}`}
            className="block h-full border-r border-background last:border-r-0"
            style={{ width: `${value}%`, background: c.color }}
          />
        );
      })}
    </span>
  );
}
