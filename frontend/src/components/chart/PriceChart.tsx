import * as React from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
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
 * PriceChart — the real financial chart, TradingView Lightweight Charts.
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
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: css("--line") },
        horzLines: { color: css("--line") },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: css("--rule"), labelBackgroundColor: css("--cobalt") },
        horzLine: { color: css("--rule"), labelBackgroundColor: css("--cobalt") },
      },
      rightPriceScale: { borderColor: css("--line") },
      timeScale: { borderColor: css("--line"), rightOffset: 3 },
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
  }, [bars, height, theme]);

  const shown = hover ?? bars.at(-1) ?? null;

  return (
    <div>
      {/* OHLC readout — updates with the crosshair, falls back to the latest bar. */}
      {shown && (
        <div className="num mb-2 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-muted">
          <span className="text-foreground">{shown.date}</span>
          <span>O {fmtPrice(shown.open)}</span>
          <span>H {fmtPrice(shown.high)}</span>
          <span>L {fmtPrice(shown.low)}</span>
          <span>C {fmtPrice(shown.close)}</span>
          {shown.volume ? <span>V {fmtVolume(shown.volume)}</span> : null}
        </div>
      )}
      <div ref={containerRef} className={cn("w-full", className)} />
    </div>
  );
}
