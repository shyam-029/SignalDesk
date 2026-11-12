import * as React from "react";
import { useNavigate } from "react-router-dom";

import { useNifty50 } from "@/lib/nifty50";
import { DataState } from "@/components/data/DataState";
import { fmtPrice, fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * The Nifty 50 today: one bar per constituent, largest company first, sized
 * by the day's move and colored by its sign (green above the zero line, red
 * below, the same as the price charts). Real stored data. Hover or focus a
 * bar for the readout; click or press Enter to open that company's page.
 */
export function CandleField({ className }: { className?: string }) {
  const navigate = useNavigate();
  const [active, setActive] = React.useState<number | null>(null);
  const list = useNifty50();
  const items = list.items;

  const W = 1200;
  const H = 300;
  const BASE = 150; // zero-change midline
  const n = Math.max(items.length, 1);
  const step = W / n;
  const maxAbs = Math.max(0.5, ...items.map((s) => Math.abs(s.change_pct ?? 0)));

  const activeItem = active != null ? items[active] : null;
  const advancers = items.filter((s) => (s.change_pct ?? 0) >= 0).length;

  return (
    <div className={cn("relative", className)}>
      <DataState
        loading={list.isLoading}
        error={list.error}
        onRetry={list.refetch}
        skeleton={<div className="h-64 w-full animate-pulse bg-surface-2" />}
        empty={!list.data || items.length === 0}
      >
        {/* Readout row: fixed height, so the chart never shifts on hover. */}
        <div
          className="num flex h-10 items-center justify-between gap-4 border-b border-line px-4 text-xs"
          aria-live="polite"
        >
          {activeItem ? (
            <p className="flex items-baseline gap-3">
              <span className="font-semibold text-foreground">
                {activeItem.symbol.replace(".NS", "")}
              </span>
              <span className="hidden text-muted sm:inline">{activeItem.name}</span>
              <span className="text-muted">{fmtPrice(activeItem.last_price)}</span>
              <span
                className={cn(
                  "font-medium",
                  (activeItem.change_pct ?? 0) >= 0 ? "text-up" : "text-down",
                )}
              >
                {fmtSignedPct(activeItem.change_pct)}
              </span>
            </p>
          ) : (
            <p className="text-faint">Hover a bar for the company; click to open it</p>
          )}
          <p className="shrink-0 text-muted">
            <span className="text-up">{advancers} up</span>
            <span className="text-faint"> · </span>
            <span className="text-down">{items.length - advancers} down</span>
          </p>
        </div>

        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full"
          role="group"
          aria-label="Nifty 50 companies, one bar each, sized by today's move and colored by its sign."
        >
          {/* Zero line + hairline guides */}
          {[50, 100, 200, 250].map((y) => (
            <line key={y} x1="0" y1={y} x2={W} y2={y} stroke="var(--line)" strokeWidth="1" opacity="0.6" />
          ))}
          <line x1="0" y1={BASE} x2={W} y2={BASE} stroke="var(--rule)" strokeWidth="1" />

          {items.map((s, i) => {
            const change = s.change_pct ?? 0;
            const up = change >= 0;
            const h = Math.max(3, (Math.abs(change) / maxAbs) * 125);
            const color = up ? "var(--up)" : "var(--down)";
            const isActive = i === active;
            const open = () => navigate(`/stocks/${encodeURIComponent(s.symbol.replace(".NS", ""))}`);
            return (
              <g
                key={s.symbol}
                role="link"
                tabIndex={0}
                aria-label={`${s.symbol.replace(".NS", "")} ${fmtSignedPct(s.change_pct)} today`}
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive((cur) => (cur === i ? null : cur))}
                onFocus={() => setActive(i)}
                onBlur={() => setActive((cur) => (cur === i ? null : cur))}
                onClick={open}
                onKeyDown={(event) => {
                  if (event.key === "Enter") open();
                }}
                className="cursor-pointer outline-none"
              >
                {/* Full-height hit area: thin bars stay easy to point at. */}
                <rect x={i * step} y={0} width={step} height={H} fill="transparent" />
                {isActive && (
                  <rect x={i * step} y={0} width={step} height={H} fill="var(--surface-2)" />
                )}
                <rect
                  x={i * step + step * 0.22}
                  y={up ? BASE - h : BASE}
                  width={step * 0.56}
                  height={h}
                  fill={color}
                  fillOpacity={active == null || isActive ? 0.9 : 0.45}
                />
              </g>
            );
          })}
        </svg>
      </DataState>
    </div>
  );
}
