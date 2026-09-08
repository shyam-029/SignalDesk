/**
 * NavChart: a dependency-free SVG area chart for a fund's NAV series.
 * Theme-aware colors, first/last labels, min/max gridlines. The backend
 * already stride-downsamples long windows, so the series is plot-ready.
 */
import { useId } from "react";

import { cn } from "@/lib/utils";

export function NavChart({
  points,
  positive,
  className,
}: {
  points: Array<{ date: string; nav: number }>;
  positive: boolean;
  className?: string;
}) {
  const gradId = useId();
  if (points.length < 2) return null;

  const w = 800;
  const h = 220;
  const padY = 12;
  const navs = points.map((p) => p.nav);
  const min = Math.min(...navs);
  const max = Math.max(...navs);
  const span = max - min || 1;
  const x = (i: number) => (i / (points.length - 1)) * w;
  const y = (v: number) => padY + (1 - (v - min) / span) * (h - padY * 2);

  const line = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.nav).toFixed(1)}`)
    .join(" ");
  const area = `${line} L${w},${h} L0,${h} Z`;
  const stroke = positive ? "var(--band-positive)" : "var(--band-weak)";
  const first = points[0];
  const last = points[points.length - 1];

  return (
    <div className={cn("relative", className)}>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="h-56 w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label={`NAV from ${first.date} to ${last.date}`}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {/* Min/max gridlines */}
        <line x1="0" y1={y(max)} x2={w} y2={y(max)} stroke="var(--line)" strokeWidth="1" strokeDasharray="3 4" />
        <line x1="0" y1={y(min)} x2={w} y2={y(min)} stroke="var(--line)" strokeWidth="1" strokeDasharray="3 4" />
        <path d={area} fill={`url(#${gradId})`} />
        <path d={line} fill="none" stroke={stroke} strokeWidth="1.8" />
        {/* Last point marker */}
        <circle cx={x(points.length - 1)} cy={y(last.nav)} r="3.5" fill={stroke} />
      </svg>
      <div className="num mt-1 flex justify-between text-xs text-faint">
        <span>
          {first.date} · {first.nav.toFixed(2)}
        </span>
        <span>
          {last.date} · {last.nav.toFixed(2)}
        </span>
      </div>
    </div>
  );
}
