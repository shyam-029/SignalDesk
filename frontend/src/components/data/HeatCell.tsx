import { fmtSignedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * HeatCell: a return figure on a tinted tile. The tint's strength is the
 * size of the move relative to `scale` (the largest absolute value in that
 * column), green for gains and red for losses, so a table of returns reads
 * as a heatmap at a glance while every number stays legible. A missing
 * value is a plain "-" with no tint: absence is never colored.
 */
export function HeatCell({
  value,
  scale,
  className,
}: {
  value: number | null;
  /** Largest absolute value in the column; sets full tint strength. */
  scale: number;
  className?: string;
}) {
  if (value == null) {
    return <span className={cn("num block px-2 py-1.5 text-right text-sm text-faint", className)}>-</span>;
  }
  const strength = scale > 0 ? Math.min(1, Math.abs(value) / scale) : 0;
  const tint = Math.round(8 + strength * 30); // 8% to 38%
  const tone = value >= 0 ? "var(--up)" : "var(--down)";
  return (
    <span
      className={cn("num block px-2 py-1.5 text-right text-sm font-medium text-foreground", className)}
      style={{ background: `color-mix(in srgb, ${tone} ${tint}%, transparent)` }}
    >
      {fmtSignedPct(value)}
    </span>
  );
}

/** Largest absolute value among the non-null entries (0 when there are none). */
export function heatScale(values: Array<number | null | undefined>): number {
  let max = 0;
  for (const v of values) if (v != null && Math.abs(v) > max) max = Math.abs(v);
  return max;
}
