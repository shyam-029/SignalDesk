import * as React from "react";
import { PanelRightClose } from "lucide-react";

import {
  useAlpha,
  usePerformance,
  useQuarterlyTrend,
  useShareholding,
  useRisk,
  useScores,
  useStockDetail,
  useValuationHistory,
} from "@/lib/hooks";
import { scoreBand } from "@/lib/semantic";
import { fmtPrice } from "@/lib/format";
import { cn } from "@/lib/utils";
import { quarterLabel } from "@/components/stock/QuarterlyTrend";
import { AskPanel } from "@/components/explain/AskPanel";

/**
 * AtAGlance: the stock page's side rail on wide screens. One line per
 * section of the report, each a link to that section, so the conclusions
 * stay in view while the reader scrolls the detail. It reuses the same
 * queries the sections run (same keys, so nothing is fetched twice) and
 * shows "-" wherever a section has no figure. It adds no numbers of its own.
 */
export function AtAGlance({
  symbol,
  onCollapse,
}: {
  symbol: string;
  onCollapse?: () => void;
}) {
  const detail = useStockDetail(symbol).data;
  const alpha = useAlpha(symbol).data;
  const scores = useScores(symbol).data;
  const perf = usePerformance(symbol).data;
  const history = useValuationHistory(symbol).data;
  const risk = useRisk(symbol).data;
  const trend = useQuarterlyTrend(symbol).data;
  const latestOwners = useShareholding(symbol).data?.quarters.at(-1);

  const pe = history?.multiples.find((m) => m.metric === "pe" && m.status === "available");
  const signal = alpha?.value_signal;
  const latestQuarter = trend?.quarters.at(-1);
  const last = detail?.quote.last_price ?? null;

  return (
    <div className="space-y-5 py-8 pl-6 pr-14">
      <div className="flex items-center justify-between">
        <p className="label-caps">At a glance</p>
        {onCollapse && (
          <button
            type="button"
            onClick={onCollapse}
            aria-label="Hide summary"
            title="Hide summary"
            className="text-faint transition-colors hover:text-foreground"
          >
            <PanelRightClose aria-hidden className="size-4" />
          </button>
        )}
      </div>

      <Group href="#alpha" title="Alpha">
        <ScoreLine label="Alpha score" value={alpha?.composite} />
        <ScoreLine label="Fundamental" value={alpha?.fundamental} small />
        <ScoreLine label="Technical" value={alpha?.technical} small />
        <ScoreLine label="Sentiment" value={alpha?.sentiment} small />
      </Group>

      <Group href="#valuation" title="Valuation">
        <Line
          label="Against peers"
          value={
            signal?.margin_pct != null && signal.metric
              ? `${signal.metric} ${signal.margin_pct > 0 ? "+" : ""}${signal.margin_pct.toFixed(0)}%`
              : "-"
          }
        />
        <Line
          label="Against own history"
          value={
            pe?.vs_median_pct != null
              ? `P/E ${pe.vs_median_pct > 0 ? "+" : ""}${pe.vs_median_pct.toFixed(0)}%`
              : "-"
          }
        />
      </Group>

      <Group href="#fundamentals" title="Fundamentals">
        <ScoreLine label="Profitability" value={scores?.profitability} small />
        <ScoreLine label="Solvency" value={scores?.solvency} small />
        <Line
          label={latestQuarter ? `Sales, ${quarterLabel(latestQuarter.period_end)}` : "Sales, latest quarter"}
          value={
            latestQuarter?.revenue_yoy_pct != null
              ? `${latestQuarter.revenue_yoy_pct > 0 ? "+" : ""}${latestQuarter.revenue_yoy_pct.toFixed(1)}%`
              : "-"
          }
        />
        <Line
          label="Profit, same quarter"
          value={
            latestQuarter?.net_income_yoy_pct != null
              ? `${latestQuarter.net_income_yoy_pct > 0 ? "+" : ""}${latestQuarter.net_income_yoy_pct.toFixed(1)}%`
              : "-"
          }
        />
      </Group>

      <Group href="#ownership" title="Ownership">
        <Line
          label="Promoters"
          value={latestOwners?.promoters != null ? `${latestOwners.promoters.toFixed(1)}%` : "-"}
        />
        <Line
          label="Institutions"
          value={
            latestOwners?.institutions != null ? `${latestOwners.institutions.toFixed(1)}%` : "-"
          }
        />
      </Group>

      <Group href="#risk" title="Risk">
        <Line
          label="Volatility a year"
          value={risk?.volatility_pct != null ? `${risk.volatility_pct.toFixed(1)}%` : "-"}
        />
        <Line
          label="Deepest fall"
          value={risk?.max_drawdown.pct != null ? `${risk.max_drawdown.pct.toFixed(1)}%` : "-"}
        />
        <Line label="Beta" value={risk?.beta != null ? risk.beta.toFixed(2) : "-"} />
      </Group>

      <Group href="#price" title="52-week range">
        <RangeLine low={perf?.low_52w ?? null} high={perf?.high_52w ?? null} last={last} />
      </Group>

      <p className="text-xs leading-relaxed text-faint">
        Percentages under Valuation are the gap to the median: below zero is cheaper.
        Quarter changes are against the same quarter last year.
      </p>

      {/* The question box, within reach while reading any section. */}
      {detail && (
        <div className="border-t border-line pt-4">
          <p className="mb-2 text-xs text-muted">Have a question about this company?</p>
          <AskPanel symbol={detail.symbol} displayName={detail.name} />
        </div>
      )}
    </div>
  );
}

function Group({
  href,
  title,
  children,
}: {
  href: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border-t border-line pt-3">
      <a
        href={href}
        className="text-xs font-semibold text-foreground underline-offset-4 hover:underline"
      >
        {title}
      </a>
      <div className="mt-2 space-y-1.5">{children}</div>
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <p className="flex items-baseline justify-between gap-3 text-xs">
      <span className="text-muted">{label}</span>
      <span className={cn("num font-medium", value === "-" && "text-faint")}>{value}</span>
    </p>
  );
}

function ScoreLine({
  label,
  value,
  small,
}: {
  label: string;
  value: number | null | undefined;
  small?: boolean;
}) {
  const band = scoreBand(value);
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className={small ? "text-muted" : "font-medium"}>{label}</span>
      <span className="flex items-center gap-2">
        <span className="block h-1 w-16 bg-line">
          {value != null && (
            <span
              className={cn("block h-full", band?.bar ?? "bg-faint")}
              style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
            />
          )}
        </span>
        <span
          className={cn(
            "num w-7 text-right font-medium",
            small ? "" : "text-sm",
            value == null ? "text-faint" : band?.text,
          )}
        >
          {value != null ? Math.round(value) : "-"}
        </span>
      </span>
    </div>
  );
}

/** Where the latest price sits between the 52-week low and high. */
function RangeLine({
  low,
  high,
  last,
}: {
  low: number | null;
  high: number | null;
  last: number | null;
}) {
  if (low == null || high == null || last == null || high <= low) {
    return <Line label="Low to high" value="-" />;
  }
  const pct = Math.max(0, Math.min(100, ((last - low) / (high - low)) * 100));
  return (
    <div>
      <div className="relative h-3">
        <div className="absolute inset-x-0 top-1.5 h-px bg-rule" />
        <span
          className="absolute top-1.5 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-cobalt"
          style={{ left: `${pct}%` }}
        />
      </div>
      <p className="num mt-1 flex justify-between text-xs text-muted">
        <span>{fmtPrice(low)}</span>
        <span>{fmtPrice(high)}</span>
      </p>
    </div>
  );
}
