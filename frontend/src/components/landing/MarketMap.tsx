import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { ScreenResult } from "@/lib/types";
import { valuationSemantics } from "@/lib/semantic";
import { cn } from "@/lib/utils";

/**
 * MarketMap: the whole ranked universe on one plate. Every stock that has
 * both fundamental scores is one dot: profitability left to right, solvency
 * bottom to top, colored by where its P/E sits against same-industry peers.
 * Move the pointer to read a company, click to open its research page, pick
 * a sector to light it up.
 *
 * All of it is the screener's own data (four cached pages of 250), plotted
 * as returned. Scores are whole numbers, so dots that would sit exactly on
 * top of each other are nudged by a fixed, symbol-derived offset smaller
 * than one score point: positions are stable between visits and never
 * random. Stocks missing either score are left off.
 *
 * On first paint the dots appear in place, growing from a point, in a
 * left-to-right sweep (CSS only, skipped under reduced motion). Nothing
 * travels across the plot.
 */

const PAGES = [1, 2, 3, 4];
const W = 640;
const H = 460;
const M = { top: 14, right: 14, bottom: 34, left: 40 };
const PW = W - M.left - M.right;
const PH = H - M.top - M.bottom;

type Status = "undervalued" | "fairly_valued" | "overvalued" | "unknown";

const STATUS_COLOR: Record<Status, string> = {
  undervalued: "var(--up)",
  fairly_valued: "var(--cobalt)",
  overvalued: "var(--down)",
  unknown: "var(--faint)",
};

const LEGEND: Array<{ key: Status; label: string }> = [
  { key: "undervalued", label: "Cheaper than peers" },
  { key: "fairly_valued", label: "In line" },
  { key: "overvalued", label: "Pricier than peers" },
  { key: "unknown", label: "No P/E verdict" },
];

interface Dot {
  r: ScreenResult;
  x: number;
  y: number;
  status: Status;
}

/** Stable sub-point offset in [-0.45, 0.45] from the symbol's characters. */
function nudge(symbol: string, salt: number): number {
  let h = salt;
  for (let i = 0; i < symbol.length; i++) h = (h * 31 + symbol.charCodeAt(i)) | 0;
  return ((Math.abs(h) % 1000) / 1000 - 0.5) * 0.9;
}

const sx = (v: number) => M.left + (v / 100) * PW;
const sy = (v: number) => M.top + PH - (v / 100) * PH;

function toStatus(raw: string | null): Status {
  return raw === "undervalued" || raw === "fairly_valued" || raw === "overvalued" ? raw : "unknown";
}

export function MarketMap({
  className,
  match,
}: {
  className?: string;
  /**
   * When given, the map is driven from outside: dots for which this returns
   * true are lit and the rest dimmed (the screener passes its filters). The
   * built-in sector picker and the table link are hidden in that mode.
   */
  match?: (r: ScreenResult) => boolean;
}) {
  const navigate = useNavigate();
  const svgRef = React.useRef<SVGSVGElement>(null);
  const [active, setActive] = React.useState<Dot | null>(null);
  const [sector, setSector] = React.useState<string>("");
  // Bumping this remounts the dot layer, which replays the reveal.
  const [run, setRun] = React.useState(0);

  const results = useQueries({
    queries: PAGES.map((page) => {
      const params = { page, limit: 250 };
      return {
        queryKey: ["screener", params],
        queryFn: () => api.screener(params),
        staleTime: 10 * 60_000,
      };
    }),
  });

  const loading = results.some((q) => q.isLoading);
  const failed = results.every((q) => q.isError);
  const loadedKey = results.map((q) => q.dataUpdatedAt).join("-");

  const { dots, total, sectors } = React.useMemo(() => {
    const rows = results.flatMap((q) => q.data?.items ?? []);
    const plotted: Dot[] = [];
    const sectorSet = new Set<string>();
    for (const r of rows) {
      if (r.profitability == null || r.solvency == null) continue;
      if (r.sector) sectorSet.add(r.sector);
      plotted.push({
        r,
        x: sx(Math.min(100, Math.max(0, r.profitability + nudge(r.symbol, 7)))),
        y: sy(Math.min(100, Math.max(0, r.solvency + nudge(r.symbol, 13)))),
        status: toStatus(r.valuation_status),
      });
    }
    return { dots: plotted, total: rows.length, sectors: [...sectorSet].sort() };
    // Recompute only when a page's data actually changes.
  }, [loadedKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const isLit = React.useMemo<(r: ScreenResult) => boolean>(
    () => match ?? ((r) => !sector || r.sector === sector),
    [match, sector],
  );

  /** Nearest dot to the pointer, within a small radius (in plot units). */
  const pick = (event: React.PointerEvent<SVGSVGElement>): Dot | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const box = svg.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * W;
    const py = ((event.clientY - box.top) / box.height) * H;
    let best: Dot | null = null;
    let bestD = 18 * 18;
    for (const d of dots) {
      if (!isLit(d.r)) continue;
      const dist = (d.x - px) ** 2 + (d.y - py) ** 2;
      if (dist < bestD) {
        bestD = dist;
        best = d;
      }
    }
    return best;
  };

  const open = (d: Dot) => navigate(`/stocks/${encodeURIComponent(d.r.symbol.replace(".NS", ""))}`);
  const activeSem = active ? valuationSemantics(active.r.valuation_status) : null;

  return (
    <div className={cn("border border-line bg-surface", className)}>
      {/* Readout: fixed height so the plot never jumps while hovering. */}
      <div className="flex h-12 items-center justify-between gap-3 border-b border-line px-4" aria-live="polite">
        {active ? (
          <p className="num flex min-w-0 items-baseline gap-3 text-xs">
            <span className="font-semibold text-foreground">{active.r.symbol.replace(".NS", "")}</span>
            <span className="hidden truncate text-muted sm:inline">{active.r.name}</span>
            <span className="shrink-0 text-muted">
              P <span className="text-foreground">{active.r.profitability}</span>
            </span>
            <span className="shrink-0 text-muted">
              S <span className="text-foreground">{active.r.solvency}</span>
            </span>
            {activeSem && (
              <span className="shrink-0 font-medium" style={{ color: STATUS_COLOR[active.status] }}>
                {activeSem.short}
              </span>
            )}
          </p>
        ) : (
          <p className="label-caps">
            {loading
              ? "Loading the universe"
              : match
                ? "Your matches, lit on the whole universe"
                : "Hundreds of companies, one dot each"}
          </p>
        )}
        {!match && <select
          value={sector}
          onChange={(e) => {
            setSector(e.target.value);
            setActive(null);
          }}
          aria-label="Highlight a sector on the map"
          className="h-8 max-w-40 shrink-0 border border-line bg-background px-2 text-xs text-foreground focus:border-cobalt focus:outline-none"
        >
          <option value="">All sectors</option>
          {sectors.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>}
      </div>

      {failed ? (
        <div className="flex items-center justify-center px-6 py-24 text-center text-sm text-muted">
          The market map could not be loaded.{" "}
          <button
            type="button"
            className="ml-2 underline underline-offset-4"
            onClick={() => results.forEach((q) => q.refetch())}
          >
            Retry
          </button>
        </div>
      ) : (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className={cn("block h-auto w-full touch-none", active && "cursor-pointer")}
          role="img"
          aria-label="Scatter of the ranked universe: profitability score across, solvency score up, colored by valuation against peers. The screener lists the same companies as a table."
          onPointerMove={(e) => setActive(pick(e))}
          onPointerLeave={() => setActive(null)}
          onClick={(e) => {
            const d = pick(e as unknown as React.PointerEvent<SVGSVGElement>);
            if (d) open(d);
          }}
        >
          <Frame />
          <Dots key={run} dots={dots} isLit={isLit} />
          {active && (
            <g pointerEvents="none">
              <line x1={active.x} y1={M.top} x2={active.x} y2={M.top + PH} stroke="var(--rule)" strokeWidth="1" />
              <line x1={M.left} y1={active.y} x2={M.left + PW} y2={active.y} stroke="var(--rule)" strokeWidth="1" />
              <circle cx={active.x} cy={active.y} r="7" fill="none" stroke="var(--ink)" strokeWidth="1.5" />
              <circle cx={active.x} cy={active.y} r="3.4" fill={STATUS_COLOR[active.status]} />
            </g>
          )}
        </svg>
      )}

      <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-2 border-t border-line px-4 py-2.5">
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {LEGEND.map((l) => (
            <li key={l.key} className="flex items-center gap-1.5 text-xs text-muted">
              <span className="size-2 rounded-full" style={{ background: STATUS_COLOR[l.key] }} aria-hidden />
              {l.label}
            </li>
          ))}
        </ul>
        <p className="text-xs text-faint">
          {total > dots.length && !loading ? "Companies missing a score are not plotted. " : ""}
          <button
            type="button"
            onClick={() => setRun((n) => n + 1)}
            className="mr-3 text-muted underline-offset-4 hover:text-foreground hover:underline"
          >
            Replay
          </button>
          {!match && <Link
            to={sector ? `/screener?sector=${encodeURIComponent(sector)}` : "/screener"}
            className="text-cobalt underline-offset-4 hover:underline dark:text-cobalt-strong"
          >
            Open as a table
          </Link>}
        </p>
      </div>
    </div>
  );
}

/** Axes, quarter guides and corner captions. Static. */
const Frame = React.memo(function Frame() {
  const ticks = [0, 25, 50, 75, 100];
  return (
    <g>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={sx(t)} y1={M.top} x2={sx(t)} y2={M.top + PH} stroke="var(--line)" strokeWidth="1" />
          <line x1={M.left} y1={sy(t)} x2={M.left + PW} y2={sy(t)} stroke="var(--line)" strokeWidth="1" />
          <text x={sx(t)} y={H - 18} textAnchor="middle" className="num" fontSize="11" fill="var(--faint)">
            {t}
          </text>
          <text x={M.left - 8} y={sy(t) + 4} textAnchor="end" className="num" fontSize="11" fill="var(--faint)">
            {t}
          </text>
        </g>
      ))}
      <text x={M.left + PW} y={H - 4} textAnchor="end" fontSize="11" fill="var(--muted)">
        Profitability score →
      </text>
      <text x={M.left} y={H - 4} fontSize="11" fill="var(--muted)">
        ↑ Solvency score
      </text>
      <text x={M.left + PW - 8} y={M.top + 16} textAnchor="end" fontSize="11" fill="var(--faint)">
        Profitable and solid
      </text>
      <text x={M.left + 8} y={M.top + PH - 8} fontSize="11" fill="var(--faint)">
        Weak on both
      </text>
    </g>
  );
});

/** The dot layer. Memoized: hovering re-renders only the highlight. */
const Dots = React.memo(function Dots({
  dots,
  isLit,
}: {
  dots: Dot[];
  isLit: (r: ScreenResult) => boolean;
}) {
  return (
    <g>
      {dots.map((d) => {
        const lit = isLit(d.r);
        return (
          <circle
            key={d.r.symbol}
            cx={d.x}
            cy={d.y}
            r={lit ? 2.7 : 1.8}
            fill={lit ? STATUS_COLOR[d.status] : "var(--rule)"}
            fillOpacity={lit ? 0.78 : 0.5}
            className="dot-fall"
            // Left-to-right sweep: the further right, the later it appears.
            style={{ animationDelay: `${Math.round(((d.x - M.left) / PW) * 1100)}ms` }}
          />
        );
      })}
    </g>
  );
});
