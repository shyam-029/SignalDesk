import * as React from "react";

import { cn } from "@/lib/utils";
import { METRIC_INFO } from "@/lib/metrics";
import { InfoDot } from "@/components/data/InfoDot";
import type { MetricInfo, MetricKey } from "@/lib/metrics";

/**
 * MetricRow — one labeled financial figure with its InfoDot.
 * Values are rendered in the mono/tabular treatment and stay NEUTRAL by
 * default; semantic color is applied only where the caller passes an explicit
 * analytical conclusion (band classes).
 */
export function MetricRow({
  metric,
  info,
  label,
  value,
  sub,
  valueClass,
  subClass,
  className,
  children,
}: {
  metric?: MetricKey;
  info?: MetricInfo;
  label?: string;
  value?: React.ReactNode;
  sub?: React.ReactNode;
  valueClass?: string;
  subClass?: string;
  className?: string;
  children?: React.ReactNode;
}) {
  const resolvedLabel = label ?? (metric ? (METRIC_INFO[metric]?.label ?? metric) : "");
  return (
    <div className={cn("flex items-baseline justify-between gap-3 py-1.5", className)}>
      <span className="flex items-center gap-1.5 text-sm text-muted">
        {resolvedLabel}
        {(metric || info) && <InfoDot metric={metric} info={info} />}
      </span>
      <span className="text-right">
        {children ?? (
          <>
            <span className={cn("num text-sm font-medium text-foreground", valueClass)}>
              {value}
            </span>
            {sub && (
              <span className={cn("mt-0.5 block text-[11px] text-faint", subClass)}>{sub}</span>
            )}
          </>
        )}
      </span>
    </div>
  );
}
