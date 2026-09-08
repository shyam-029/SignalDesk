import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { useFund } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * FundDetailPage: one fund's stored NAV series and windowed returns. Every
 * point is a stored row (AMFI daily file, plus the documented backfill
 * fallback); the backend computes the returns, the page only renders them.
 */
export default function FundDetailPage() {
  const { fundId } = useParams();
  const id = fundId != null && /^\d+$/.test(fundId) ? Number(fundId) : undefined;
  const query = useFund(id);
  const fund = query.data;

  const returns: Array<[string, number | null]> = [
    ["1M", fund?.return_1m_pct ?? null],
    ["3M", fund?.return_3m_pct ?? null],
    ["6M", fund?.return_6m_pct ?? null],
  ];

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
      <Link
        to="/funds"
        className="label-caps inline-flex items-center gap-1.5 text-muted transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden />
        All funds
      </Link>

      <div className="mt-4">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
        >
          {fund && (
            <>
              <p className="label-caps">{fund.category ?? "Fund"}</p>
              <h1 className="mt-1 font-display text-3xl font-semibold">{fund.name}</h1>
              <p className="num mt-1 text-xs text-faint">
                AMFI {fund.amfi_code} · {fund.plan}
                {fund.option ? ` · ${fund.option}` : ""}
              </p>

              <div className="mt-6 grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
                <StatBlock
                  label="Latest NAV"
                  value={fund.latest_nav != null ? fmtPrice(fund.latest_nav) : "-"}
                  sub={fund.nav_date ?? undefined}
                />
                {returns.map(([label, value]) => (
                  <StatBlock
                    key={label}
                    label={`Return ${label}`}
                    value={fmtSignedPct(value)}
                    tone={
                      value == null
                        ? "faint"
                        : value >= 0
                          ? "positive"
                          : "weak"
                    }
                  />
                ))}
              </div>

              <div className="mt-8 border border-line bg-surface">
                <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-3">
                  <p className="label-caps">NAV history</p>
                  <p className="num text-xs text-faint">
                    {fund.nav_points} stored point{fund.nav_points === 1 ? "" : "s"}
                    {fund.history_start && fund.history_end
                      ? ` · ${fund.history_start} to ${fund.history_end}`
                      : ""}
                  </p>
                </div>
                {fund.items.length === 0 ? (
                  <p className="px-5 py-6 text-sm text-muted">
                    No NAV points stored yet; history builds nightly from the
                    official AMFI file.
                  </p>
                ) : (
                  <div className="max-h-96 overflow-y-auto">
                    <table className="w-full border-collapse text-left">
                      <tbody>
                        {[...fund.items].reverse().map((point) => (
                          <tr key={point.date} className="border-b border-line last:border-b-0">
                            <td className="num px-5 py-2 text-sm">{point.date}</td>
                            <td className="num px-3 py-2 text-right text-sm font-medium">
                              {fmtPrice(point.nav)}
                            </td>
                            <td className="px-5 py-2 text-right text-xs text-faint">
                              {point.source}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <p className="mt-4 text-xs leading-relaxed text-faint">
                NAVs are daily close values from AMFI (official) with a
                documented fallback backfill marked per row. Returns are
                computed from stored history only. Not investment advice.
              </p>
            </>
          )}
        </DataState>
      </div>
    </div>
  );
}

function StatBlock({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "positive" | "weak" | "faint";
}) {
  const toneClass =
    tone === "positive"
      ? "text-band-positive"
      : tone === "weak"
        ? "text-band-weak"
        : tone === "faint"
          ? "text-faint"
          : "text-foreground";
  return (
    <div className="bg-surface p-5">
      <p className="label-caps">{label}</p>
      <p className={cn("num mt-1 text-2xl font-medium", toneClass)}>{value}</p>
      {sub && <p className="num mt-0.5 text-xs text-faint">{sub}</p>}
    </div>
  );
}
