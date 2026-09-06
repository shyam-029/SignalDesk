import * as React from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";

import { cn } from "@/lib/utils";
import { fmtPrice, fmtVolume } from "@/lib/format";
import { useTheme } from "@/components/layout/ThemeProvider";
import type { PriceBar } from "@/lib/types";

/**
 * PriceChart: the real financial chart, TradingView Lightweight Charts.
 * Candlesticks colored with the semantic positive/negative tokens (never a
 * decorative rainbow), crosshair + OHLC legend, theme-aware, resizes with its
 * container. Range selection is handled by the parent via the prices hook.
 */
export function PriceChart({
  bars,
  height = 380,
  className,
}: {
  bars: PriceBar[];
  height?: number;
  className?: string;
}) {
  const containerRef = React.useRef<HTMLDivElement>(null);  const chartRef = React.useRef<IChartApi | null>(null);
  const seriesRef = React.useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [hover, setHover] = React.useState<PriceBar | null>(null);
  // Bumped when a previously zero-width (hidden) container becomes measurable.
  const [mountTick, setMountTick] = React.useState(0);
  const { theme } = useTheme();

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // Hidden right now (e.g. inside a collapsed section): wait for a real
    // width instead of building a broken zero-width chart.
    if (el.clientWidth === 0) {
      const gate = new ResizeObserver(() => {
        if (el.clientWidth > 0) setMountTick((t) => t + 1);
      });
      gate.observe(el);
      return () => gate.disconnect();
    }

    const styles = getComputedStyle(document.documentElement);
    const css = (name: string) => styles.getPropertyValue(name).trim();

    const chart = createChart(el, {
      width: el.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: css("--muted"),
        // Only weights 500+ of IBM Plex Mono are loaded, so the canvas's
        // implicit 400 request resolves to the 500 face per CSS font matching.
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 12,
      },
      grid: {
        // Horizontal reference lines only: calendar tick spacing is uneven
        // in trading days, so vertical lines made the grid look irregular.
        vertLines: { visible: false },
        horzLines: { color: css("--line") },
      },
      crosshair: {
        // Single vertical tracker with the date labeled on the time axis;
        // values live in the OHLC readout above, so no horizontal price
        // line/bubble competing with the candles.
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
      // The chart shows exactly the data the backend provides: no drag
      // panning, no pinch/wheel scaling, no axis dragging. A stray mouse
      // drag can no longer shrink or blank the view.
      handleScale: false,
      handleScroll: false,
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: css("--band-positive"),
      downColor: css("--band-weak"),
      wickUpColor: css("--band-positive"),
      wickDownColor: css("--band-weak"),
      borderVisible: false,
    });

    series.setData(
      bars.map(
        (b): CandlestickData<Time> => ({
          time: b.date as Time,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        }),
      ),
    );
    chart.timeScale().fitContent();

    chart.subscribeCrosshairMove((param) => {
      if (!param.time) {
        setHover(null);
        return;
      }
      const d = param.seriesData.get(series) as CandlestickData<Time> | undefined;
      if (!d) {
        setHover(null);
        return;
      }
      setHover({
        date: String(param.time),
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
        volume: 0,
      });
    });

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    observer.observe(el);

    chartRef.current = chart;
    seriesRef.current = series;

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [bars, height, theme, mountTick]);

  const shown = hover ?? bars.at(-1) ?? null;
  const upCandle =
    shown != null && shown.close >= shown.open;

  return (
    <div>
      {/* OHLC readout: prominent, updates with the crosshair, falls back to
          the latest bar. The close is market-colored (up green / down red). */}
      {shown && (
        <div className="mb-3 flex flex-wrap items-baseline gap-x-5 gap-y-1 border border-line bg-surface-2/60 px-3 py-2 text-sm">
          <span className="num font-semibold text-foreground">{shown.date}</span>
          <span className="num text-muted">
            O <span className="font-medium text-foreground">{fmtPrice(shown.open)}</span>
          </span>
          <span className="num text-muted">
            H <span className="font-medium text-foreground">{fmtPrice(shown.high)}</span>
          </span>
          <span className="num text-muted">
            L <span className="font-medium text-foreground">{fmtPrice(shown.low)}</span>
          </span>
          <span
            className={cn(
              "num",
              upCandle ? "text-band-positive" : "text-band-weak",
            )}
          >
            C <span className="font-semibold">{fmtPrice(shown.close)}</span>
          </span>
          {shown.volume ? (
            <span className="num text-muted">
              V <span className="font-medium text-foreground">{fmtVolume(shown.volume)}</span>
            </span>
          ) : null}
        </div>
      )}
      <div ref={containerRef} className={cn("w-full", className)} />
    </div>
  );
}
