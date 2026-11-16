import * as React from "react";
import { Link } from "react-router-dom";

import { useEtfs } from "@/lib/hooks";
import type { EtfSummary } from "@/lib/types";
import { DataState } from "@/components/data/DataState";
import { HeatCell, heatScale } from "@/components/data/HeatCell";
import { SectionHeader } from "@/components/data/SectionHeader";
import { StatTiles } from "@/components/data/StatTiles";
import { fmtDate, fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * EtfsPage: the ETF catalog as a one-year league table. Each fund is a row
 * with a bar that grows right (gain) or left (loss) from a shared zero line,
 * so the whole shelf can be compared without reading a single number; the
 * day's move sits beside it as a heat tile. Rows link to the standard
 * research page: ETFs reuse the equity price pipeline and never mix into the
 * equity screener or stock list. A missing figure is "-" and has no bar.
 *
 * The "what it tracks" groups are read from each fund's name (the API carries
 * no type yet), so a fund whose name matches no rule lands in "Other".
 */

type SortKey = "return_1y" | "change" | "symbol";

const SORTS: Array<{ key: SortKey; label: string }> = [
  { key: "return_1y", label: "1Y return" },
  { key: "change", label: "Today" },
  { key: "symbol", label: "A to Z" },
];

const TYPES = [
  "Broad market",
  "Sector and theme",
  "Gold and silver",
  "International",
  "Debt and liquid",
  "Other",
] as const;
type EtfType = (typeof TYPES)[number];

// Order matters: "Nifty Bank" is a sector fund, not a broad-market one.
const TYPE_RULES: Array<[EtfType, RegExp]> = [
  ["Gold and silver", /GOLD|SILVER/],
  ["International", /NASDAQ|FANG|S&P|HANG SENG|MSCI|NYSE|\bUS\b|CHINA|JAPAN|GLOBAL/],
  ["Debt and liquid", /LIQUID|GILT|G-?SEC|BOND|\bSDL\b|MONEY|OVERNIGHT/],
  [
    "Sector and theme",
    /BANK|\bPSU\b|\bIT\b|INFRA|PHARMA|HEALTH|AUTO|FMCG|CONSUM|ENERGY|METAL|REALTY|MFG|MANUFACTUR|DEFEN[CS]E|CPSE|DIVIDEND|MOMENTUM|QUALITY|VALUE|LOW VOL|ALPHA|\bESG\b|SHARIAH|FINANCIAL|PRIVATE|\bMNC\b|COMMODIT/,
  ],
  [
    "Broad market",
    /NIFTY ?50|SENSEX|NEXT ?50|JUNIOR|MID ?CAP|SMALL ?CAP|NIFTY ?100|NIFTY ?200|NIFTY ?500|BSE ?500|TOTAL MARKET|LARGE ?CAP/,
  ],
];

function etfType(etf: EtfSummary): EtfType {
  const text = `${etf.symbol} ${etf.name}`.toUpperCase();
  return TYPE_RULES.find(([, re]) => re.test(text))?.[0] ?? "Other";
}

function sortEtfs(items: EtfSummary[], key: SortKey): EtfSummary[] {
  const desc = (a: number | null, b: number | null) =>
    a == null ? (b == null ? 0 : 1) : b == null ? -1 : b - a; // nulls last
  return [...items].sort((a, b) =>
    key === "symbol"
      ? a.symbol.localeCompare(b.symbol)
      : key === "change"
        ? desc(a.change_pct, b.change_pct)
        : desc(a.return_1y_pct, b.return_1y_pct),
  );
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

const short = (symbol: string) => symbol.replace(".NS", "");

const chipClass = (active: boolean) =>
  cn(
    "border px-2.5 py-1 text-xs font-medium transition-colors",
    active
      ? "border-cobalt bg-surface-2 text-foreground"
      : "border-line text-muted hover:text-foreground",
  );

function EtfLink({ etf }: { etf: EtfSummary }) {
  return (
    <Link to={`/stocks/${encodeURIComponent(etf.symbol)}`} className="group block min-w-0">
      <span className="tkr block text-sm font-semibold group-hover:text-cobalt group-hover:underline dark:group-hover:text-cobalt-strong">
        {short(etf.symbol)}
      </span>
      <span className="block max-w-72 truncate text-xs text-muted">{etf.name}</span>
    </Link>
  );
}

export default function EtfsPage() {
  const query = useEtfs();
  const etfs = query.data;
  const [sort, setSort] = React.useState<SortKey>("return_1y");
  const [type, setType] = React.useState<EtfType | "">("");

  const typed = React.useMemo(
    () => (etfs?.items ?? []).map((etf) => ({ etf, type: etfType(etf) })),
    [etfs],
  );
  const typeCounts = React.useMemo(() => {
    const counts = new Map<EtfType, number>();
    for (const t of typed) counts.set(t.type, (counts.get(t.type) ?? 0) + 1);
    return counts;
  }, [typed]);
  const items = React.useMemo(
    () =>
      sortEtfs(
        typed.filter((t) => !type || t.type === type).map((t) => t.etf),
        sort,
      ),
    [typed, type, sort],
  );
  const typeOf = React.useMemo(() => new Map(typed.map((t) => [t.etf.symbol, t.type])), [typed]);

  const yearScale = heatScale(items.map((e) => e.return_1y_pct));
  const dayScale = heatScale(items.map((e) => e.change_pct));
  const asOf = items.find((e) => e.as_of)?.as_of ?? null;

  const years = items.map((e) => e.return_1y_pct).filter((v): v is number => v != null);
  const days = items.map((e) => e.change_pct).filter((v): v is number => v != null);
  const mid = median(years);
  const best = items.reduce<EtfSummary | null>(
    (top, e) =>
      e.return_1y_pct != null && (top == null || e.return_1y_pct > (top.return_1y_pct ?? -Infinity))
        ? e
        : top,
    null,
  );
  const upToday = days.filter((v) => v > 0).length;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 md:px-6">
      <SectionHeader
        kicker="Exchange-traded funds"
        title="One-year league table"
        aside={
          <div className="flex items-center gap-1" role="group" aria-label="Sort ETFs">
            {SORTS.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => setSort(s.key)}
                aria-pressed={sort === s.key}
                className={chipClass(sort === s.key)}
              >
                {s.label}
              </button>
            ))}
          </div>
        }
      />
      <p className="max-w-2xl text-sm leading-relaxed text-muted">
        Funds you buy and sell on the exchange like a share, priced from the same daily pipeline
        as stocks. Bars share one zero line and one scale, so their lengths compare directly.
        {asOf ? ` Daily close data, latest bar ${fmtDate(asOf)}.` : ""}
      </p>

      {items.length > 0 && (
        <StatTiles
          className="mt-6"
          tiles={[
            { label: type ? "In this group" : "ETFs tracked", value: String(items.length) },
            {
              label: "Up today",
              value: days.length ? `${upToday} of ${days.length}` : "-",
            },
            {
              label: "Typical 1Y return",
              value: fmtSignedPct(mid),
              tone: mid == null ? undefined : mid >= 0 ? "up" : "down",
              note: "The middle fund",
            },
            {
              label: "Best over 1Y",
              value: best ? short(best.symbol) : "-",
              note: best ? fmtSignedPct(best.return_1y_pct) : undefined,
            },
          ]}
        />
      )}

      {typed.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1" role="tablist" aria-label="What it tracks">
          <button type="button" role="tab" aria-selected={type === ""} onClick={() => setType("")} className={chipClass(type === "")}>
            All <span className="num ml-1 text-faint">{typed.length}</span>
          </button>
          {TYPES.filter((t) => typeCounts.has(t)).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={type === t}
              onClick={() => setType(t)}
              className={chipClass(type === t)}
            >
              {t} <span className="num ml-1 text-faint">{typeCounts.get(t)}</span>
            </button>
          ))}
        </div>
      )}

      <div className="mt-4">
        <DataState
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          empty={Boolean(etfs) && etfs?.total === 0}
          emptyTitle="No ETFs catalogued yet"
          emptyMessage="The ETF catalog fills in when ingestion runs. Nothing is invented in the meantime."
        >
          {items.length > 0 && (
            <>
              {/* Phones: one card a fund. */}
              <ul className="border border-line bg-surface md:hidden">
                {items.map((etf) => (
                  <li key={etf.symbol} className="border-b border-line p-4 last:border-b-0">
                    <div className="flex items-start justify-between gap-3">
                      <EtfLink etf={etf} />
                      <div className="shrink-0 text-right">
                        <p className="num text-sm">{etf.last_price != null ? fmtPrice(etf.last_price) : "-"}</p>
                        <p
                          className={cn(
                            "num text-xs",
                            etf.change_pct == null
                              ? "text-faint"
                              : etf.change_pct >= 0
                                ? "text-up"
                                : "text-down",
                          )}
                        >
                          {fmtSignedPct(etf.change_pct)} today
                        </p>
                      </div>
                    </div>
                    <div className="mt-3">
                      <p className="label-caps mb-1">One year</p>
                      <DivergingBar value={etf.return_1y_pct} scale={yearScale} compact />
                    </div>
                  </li>
                ))}
              </ul>

              <div className="hidden overflow-x-auto border border-line bg-surface md:block">
                <table className="w-full min-w-[720px] border-collapse text-left">
                  <thead>
                    <tr className="border-b border-line">
                      <th scope="col" className="label-caps px-5 py-3">Fund</th>
                      <th scope="col" className="label-caps px-3 py-3">Tracks</th>
                      <th scope="col" className="label-caps px-3 py-3 text-right">Price</th>
                      <th scope="col" className="label-caps w-24 px-3 py-3 text-right">Today</th>
                      <th scope="col" className="label-caps px-5 py-3">One year</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((etf) => (
                      <tr key={etf.symbol} className="border-b border-line last:border-b-0 hover:bg-surface-2/50">
                        <td className="px-5 py-2.5">
                          <EtfLink etf={etf} />
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-xs text-muted">
                          {typeOf.get(etf.symbol)}
                        </td>
                        <td className="num px-3 py-2.5 text-right text-sm">
                          {etf.last_price != null ? fmtPrice(etf.last_price) : "-"}
                        </td>
                        <td className="p-0.5">
                          <HeatCell value={etf.change_pct} scale={dayScale} />
                        </td>
                        <td className="px-5 py-2.5">
                          <DivergingBar value={etf.return_1y_pct} scale={yearScale} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </DataState>
      </div>

      <p className="mt-4 max-w-3xl text-xs leading-relaxed text-faint">
        "-" means the figure is not stored yet (a fund needs a year of bars for the one-year
        return). The "Tracks" group is read from the fund's name. Every ETF's daily NAV and
        longer returns are on the{" "}
        <Link to="/funds" className="underline">
          mutual funds
        </Link>{" "}
        board. Not investment advice.
      </p>
    </div>
  );
}

/** A bar from a centered zero line: right for a gain, left for a loss. */
function DivergingBar({
  value,
  scale,
  compact = false,
}: {
  value: number | null;
  scale: number;
  compact?: boolean;
}) {
  if (value == null) return <span className="num text-sm text-faint">-</span>;
  const half = scale > 0 ? Math.min(50, (Math.abs(value) / scale) * 50) : 0;
  const up = value >= 0;
  return (
    <span className="flex items-center gap-3">
      <span className={cn("relative block h-4 flex-1", !compact && "min-w-40")} aria-hidden>
        <span className="absolute inset-y-0 left-1/2 w-px bg-rule" />
        <span
          className="absolute inset-y-0.5"
          style={{
            background: up ? "var(--up)" : "var(--down)",
            width: `${half}%`,
            left: up ? "50%" : `${50 - half}%`,
          }}
        />
      </span>
      <span className={cn("num w-16 shrink-0 text-right text-sm font-medium", up ? "text-up" : "text-down")}>
        {fmtSignedPct(value)}
      </span>
    </span>
  );
}
