import * as React from "react";
import {
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
  type WhitespaceData,
} from "lightweight-charts";

import { cn } from "@/lib/utils";
import { useTheme } from "@/components/layout/ThemeProvider";

export interface TimeSeriesPoint {
  time: string;
  /** Null renders a whitespace point: the line breaks instead of faking a value. */
  value: number | null;
}

export interface TimeSeriesLine {
  key: string;
  label: string;
  /** CSS custom property name (e.g. "--cobalt"), resolved against the theme. */
  color: string;
  data: TimeSeriesPoint[];
  /** Render as a histogram (MACD pane / bar chart), defaults to a line. */
  histogram?: boolean;
  width?: 1 | 2;
  /** Show a marker at every point (useful for sparse series). */
  points?: boolean;
}

/**
 * TimeSeriesChart: the shared Lightweight Charts panel for research series
 * (alpha history, technical indicator series). Lines support null gaps via
 * whitespace points, the crosshair readout lists every series value at the
 * hovered date, and the chart is theme-aware and container-resizing like
 * PriceChart. Values arrive pre-scaled from the backend; this component only
 * renders.
 */
export function TimeSeriesChart({
  lines,
  height = 240,
  className,
  valueFormatter,
}: {
  lines: TimeSeriesLine[];
  height?: number;
  className?: string;
  valueFormatter?: (v: number) => string;
}) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const chartRef = React.useRef<IChartApi | null>(null);
  const seriesRefs = React.useRef<Map<string, ISeriesApi<"Line" | "Histogram">>>(new Map());
  const [hoverTime, setHoverTime] = React.useState<string | null>(null);
  const { theme } = useTheme();

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const styles = getComputedStyle(document.documentElement);
    const css = (name: string) => styles.getPropertyValue(name).trim();

    const chart = createChart(el, {
      width: el.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: css("--muted"),
        // Only weights 500+ of IBM Plex Mono are loaded, so the canvas's
        // implicit 400 request resolves to the 500 face per CSS matching.
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 12,
      },
      grid: {
        vertLines: { color: css("--line") },
        horzLines: { color: css("--line") },
      },
      crosshair: {
        // A single vertical tracker: the date under the cursor is labeled on
        // the time axis and the readout above lists every series value at
        // that date. No horizontal line/price bubble — the readout carries
        // the values without cluttering the price scale.
        mode: CrosshairMode.Normal,
        vertLine: {
          color: css("--faint"),
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: css("--cobalt"),
        },
        horzLine: { visible: false, labelVisible: false },
      },
      rightPriceScale: { borderColor: css("--line") },
      timeScale: { borderColor: css("--line"), rightOffset: 3 },
      // Fixed viewport: exactly the data the backend provides, no drag
      // panning or pinch/wheel scaling (a stray drag could shrink or blank
      // the chart).
      handleScale: false,
      handleScroll: false,
    });

    const refs = new Map<string, ISeriesApi<"Line" | "Histogram">>();
    for (const line of lines) {
      const color = css(line.color) || css("--faint");
      const series =
        line.histogram
          ? chart.addSeries(HistogramSeries, { color, priceLineVisible: false, base: 0 })
          : chart.addSeries(LineSeries, {
              color,
              lineWidth: line.width ?? 2,
              priceLineVisible: false,
              lastValueVisible: false,
              pointMarkersVisible: line.points ?? false,
            });
      series.setData(toLineData(line.data));
      refs.set(line.key, series);
    }
    chart.timeScale().fitContent();

    chart.subscribeCrosshairMove((param) => {
      setHoverTime(param.time ? String(param.time) : null);
    });

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    observer.observe(el);

    chartRef.current = chart;
    seriesRefs.current = refs;

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRefs.current = new Map();
    };
    // Rebuild when the data shape or theme changes; parents memoize `lines`.
  }, [lines, height, theme]);

  const rows = lines.map((line) => {
    const byTime = hoverTime
      ? line.data.find((p) => p.time === hoverTime)
      : lastDefined(line.data);
    return {
      key: line.key,
      label: line.label,
      color: line.color,
      value: byTime?.value ?? null,
    };
  });

  return (
    <div>
      {rows.length > 0 && (
        <div className="num mb-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
          {hoverTime && <span className="text-foreground">{hoverTime}</span>}
          {rows.map((r) => (
            <span key={r.key} className="flex items-baseline gap-1.5">
              <span
                aria-hidden
                className="inline-block size-1.5 rounded-full"
                style={{ backgroundColor: `var(${r.color})` }}
              />
              {r.label}
              <span className="text-foreground">
                {r.value == null ? "-" : valueFormatter ? valueFormatter(r.value) : r.value.toFixed(2)}
              </span>
            </span>
          ))}
        </div>
      )}
      <div ref={containerRef} className={cn("w-full", className)} />
    </div>
  );
}

/** Latest point that actually carries a value (no findLast in the ts target). */
function lastDefined(data: TimeSeriesPoint[]): TimeSeriesPoint | null {
  for (let i = data.length - 1; i >= 0; i--) {
    if (data[i].value != null) return data[i];
  }
  return null;
}

function toLineData(data: TimeSeriesPoint[]): (LineData<Time> | WhitespaceData<Time>)[] {
  const out: (LineData<Time> | WhitespaceData<Time>)[] = [];
  for (const point of data) {
    // Whitespace points keep the time axis continuous through null gaps
    // instead of drawing a misleading connection or a fabricated value.
    out.push(
      point.value == null
        ? { time: point.time as Time }
        : { time: point.time as Time, value: point.value },
    );
  }
  return out;
}
