import * as React from "react";
import { animate, useInView } from "framer-motion";

import { cn } from "@/lib/utils";
import { scoreBand } from "@/lib/semantic";
import type { MetricKey } from "@/lib/metrics";
import { InfoDot } from "@/components/data/InfoDot";

/**
 * ScoreBlock: SignalDesk's signature analytical object.
 *
 * NOT a circular gauge: a large tabular number, its band word, and a segmented
 * analytical scale. The whole treatment responds to the score band:
 *   tint (subtle) → border (medium) → score/segments (strong).
 * The number counts up when revealed and morphs smoothly when the score
 * changes (e.g. 59 → 82 while switching stocks), color included.
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
  /** Render without the score-tinted surface (embed inside a tinted parent). */
  flat?: boolean;
  showBand?: boolean;
  suffix?: string;
  className?: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const [displayed, setDisplayed] = React.useState<number | null>(null);

  const band = scoreBand(score);

  // Count up from 0 when first seen; morph between values on later changes.
  React.useEffect(() => {
    if (score == null || band == null) {
      setDisplayed(null);
      return;
    }
    const controls = animate(displayed ?? 0, score, {
      duration: displayed == null ? (inView ? 0.9 : 0) : 0.6,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => setDisplayed(Math.round(v)),
    });
    return () => controls.stop();
  }, [score, inView, band]); // eslint-disable-line react-hooks/exhaustive-deps

  if (score == null || band == null) {
    return <ScoreUnavailable label={label} metric={metric} className={className} />;
  }

  const shown = displayed ?? 0;
  const sizes = {
    sm: { num: "text-2xl", label: "text-xs" },
    md: { num: "text-4xl", label: "text-xs" },
    lg: { num: "text-6xl", label: "text-sm" },
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
          {shown}
          <span className="ml-1 text-[max(0.4em,12px)] font-medium text-faint">{suffix}</span>
        </p>
        {showBand && (
          <span
            className={cn(
              "mb-1 border px-1.5 py-0.5 text-xs font-semibold uppercase tracking-[0.08em]",
              band.text,
              band.border,
            )}
          >
            {band.label}
          </span>
        )}
      </div>
      <SegmentedBar score={score} band={band} />
    </div>
  );

  if (flat) return body;

  return (
    <div ref={ref} className={cn("border bg-surface p-4", band.border, `${band.bg.replace("/10", "/6")}`)}>
      {body}
    </div>
  );
}

/** Subtle band-tinted surface. The tint stays light; the score carries color. */
export function SegmentedBar({
  score,
  band,
  segments = 20,
  className,
}: {
  score: number;
  band: { bar: string };
  segments?: number;
  className?: string;
}) {
  const filled = Math.round((score / 100) * segments);
  return (
    <div className={cn("flex gap-[3px]", className)} aria-hidden>
      {Array.from({ length: segments }, (_, i) => (
        <span
          key={i}
          className={cn(
            "h-1.5 flex-1 transition-colors duration-500",
            i < filled ? band.bar : "bg-line opacity-70",
          )}
          style={{ transitionDelay: `${Math.min(i * 18, 500)}ms` }}
        />
      ))}
    </div>
  );
}

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
