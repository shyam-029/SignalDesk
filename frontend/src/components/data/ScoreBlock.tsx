import { cn } from "@/lib/utils";
import { scoreBand } from "@/lib/semantic";
import type { MetricKey } from "@/lib/metrics";
import { InfoDot } from "@/components/data/InfoDot";

/**
 * ScoreBlock: a score stated plainly. A large tabular number, its band word,
 * and one thin scale bar. The band colors the number and the bar; the surface
 * stays neutral. Nothing counts up or animates: the number is the number.
 */
export function ScoreBlock({
  score,
  label,
  metric,
  size = "md",
  showBand = true,
  flat = false,
  suffix = "/100",
  className,
}: {
  score: number | null;
  label?: string;
  metric?: MetricKey;
  size?: "sm" | "md" | "lg";
  /** Render without its own bordered surface (embed inside a parent panel). */
  flat?: boolean;
  showBand?: boolean;
  suffix?: string;
  className?: string;
}) {
  const band = scoreBand(score);

  if (score == null || band == null) {
    return <ScoreUnavailable label={label} metric={metric} className={className} />;
  }

  const sizes = {
    sm: { num: "text-2xl", label: "text-xs" },
    md: { num: "text-4xl", label: "text-xs" },
    lg: { num: "text-6xl", label: "text-xs" },
  } as const;

  const body = (
    <div className={cn("flex h-full w-full flex-col justify-between gap-3", className)}>
      {label && (
        <p className={cn("label-caps flex items-center gap-1.5", sizes[size].label)}>
          {label}
          {metric && <InfoDot metric={metric} className="size-3.5" />}
        </p>
      )}
      <div className="flex items-end justify-between gap-2">
        <p className={cn("num font-medium leading-none", sizes[size].num, band.text)}>
          {Math.round(score)}
          <span className="ml-1 text-[max(0.3em,12px)] font-medium text-faint">{suffix}</span>
        </p>
        {showBand && (
          <span className={cn("mb-1 text-xs font-semibold", band.text)}>
            {band.label}
          </span>
        )}
      </div>
      <ScaleBar score={score} band={band} />
    </div>
  );

  if (flat) return body;

  return <div className="border border-line bg-surface p-4">{body}</div>;
}

/** One continuous 0-100 scale with the band-colored fill. */
export function ScaleBar({
  score,
  band,
  className,
}: {
  score: number | null;
  band: { bar: string } | null;
  className?: string;
}) {
  const pct = Math.min(100, Math.max(0, score ?? 0));
  return (
    <div className={cn("h-1 w-full bg-line", className)} aria-hidden>
      <div className={cn("h-full", band?.bar ?? "bg-faint")} style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Kept under its old name for existing imports. */
export const SegmentedBar = ScaleBar;

function ScoreUnavailable({
  label,
  metric,
  className,
}: {
  label?: string;
  metric?: MetricKey;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-full w-full flex-col justify-between gap-3 border border-dashed border-line p-4",
        className,
      )}
    >
      {label && (
        <p className="label-caps flex items-center gap-1.5 text-xs">
          {label}
          {metric && <InfoDot metric={metric} className="size-3.5" />}
        </p>
      )}
      <p className="num text-2xl text-faint">-</p>
      <p className="text-xs leading-snug text-faint">
        Score unavailable. Not enough data to compute it.
      </p>
    </div>
  );
}
