import { METRIC_INFO, type MetricInfo, type MetricKey } from "@/lib/metrics";
import { cn } from "@/lib/utils";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Tooltip } from "@/components/ui/tooltip";

/**
 * InfoDot — the information affordance for a metric.
 *
 * Hover/focus shows the short definition (tooltip). Activating opens a popover
 * with the methodology; entries carrying `longer` expose an expandable section
 * inside the popover. Essential methodology is therefore never hidden behind
 * hover alone — it is always reachable via keyboard focus + Enter/Space.
 */
export function InfoDot({
  metric,
  info,
  className,
}: {
  /** Key into METRIC_INFO, or pass `info` directly for ad-hoc entries. */
  metric?: MetricKey;
  info?: MetricInfo;
  className?: string;
}) {
  const resolved: MetricInfo | undefined = info ?? (metric ? METRIC_INFO[metric] : undefined);
  if (!resolved) return null;

  const hasPopover = Boolean(resolved.method || resolved.longer);

  const dot = (
    <span
      tabIndex={hasPopover ? 0 : undefined}
      className={cn(
        "inline-flex size-4 cursor-help items-center justify-center rounded-full",
        "border border-line text-[9px] font-semibold text-faint transition-colors",
        "hover:border-cobalt hover:text-cobalt dark:hover:text-cobalt-strong",
        className,
      )}
      aria-label={`About ${resolved.label}`}
      role={hasPopover ? "button" : undefined}
    >
      i
    </span>
  );

  const tooltipBody = (
    <span>
      <span className="font-semibold">{resolved.label}.</span> {resolved.short}
      {hasPopover && <span className="mt-1 block text-faint">Click for methodology.</span>}
    </span>
  );

  if (!hasPopover) {
    return (
      <Tooltip content={tooltipBody}>
        <span className="inline-flex">{dot}</span>
      </Tooltip>
    );
  }

  return (
    <Popover>
      <Tooltip content={tooltipBody}>
        <PopoverTrigger asChild>
          <span className="inline-flex">{dot}</span>
        </PopoverTrigger>
      </Tooltip>
      <PopoverContent>
        <InfoContent info={resolved} />
      </PopoverContent>
    </Popover>
  );
}

/**
 * The popover body (definition + methodology + expandable context). Exported
 * so tests can assert the content without jsdom-hostile portal interactions.
 */
export function InfoContent({ info }: { info: MetricInfo }) {
  return (
    <div>
      <p className="text-sm font-semibold">{info.label}</p>
      <p className="mt-1.5 text-xs leading-relaxed text-muted">{info.short}</p>
      {info.method && (
        <div className="mt-3 border-t border-line pt-3">
          <p className="label-caps">Methodology</p>
          <p className="mt-1 text-xs leading-relaxed text-muted">{info.method}</p>
        </div>
      )}
      {info.longer && (
        <details className="group mt-3 border-t border-line pt-3">
          <summary className="cursor-pointer text-xs font-medium text-cobalt dark:text-cobalt-strong">
            More context
          </summary>
          <p className="mt-1.5 text-xs leading-relaxed text-muted">{info.longer}</p>
        </details>
      )}
    </div>
  );
}
