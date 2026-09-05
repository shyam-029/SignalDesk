import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import {
  useAlpha,
  usePrices,
  useStockDetail,
  useTechnicals,
} from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { ScoreBlock } from "@/components/data/ScoreBlock";
import { PriceChart } from "@/components/chart/PriceChart";
import { Reveal } from "@/components/motion/Reveal";
import { Button } from "@/components/ui/button";
import { fmtMarketCap, fmtPrice, fmtSignedPct } from "@/lib/format";

/**
 * ProductPreview: the real product, fed by the real API. If the backend is
 * down, the section shows the real error state instead of a fake screenshot.
 */
export function ProductPreview() {
  const symbol = "RELIANCE";
  const detail = useStockDetail(symbol);
  const alpha = useAlpha(symbol);
  const technicals = useTechnicals(symbol);
  const prices = usePrices(symbol, "6mo");

  const loading =
    detail.isLoading || alpha.isLoading || technicals.isLoading || prices.isLoading;
  const error = detail.error ?? alpha.error ?? technicals.error ?? prices.error;

  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 md:px-6 md:py-28">
        <Reveal className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="label-caps mb-3">The research screen</p>
            <h2 className="max-w-2xl font-display text-3xl font-semibold leading-tight md:text-4xl">
              One page per company. Everything that matters, on one page.
            </h2>
          </div>
          <Button asChild variant="outline" className="gap-2">
            <Link to="/stocks/RELIANCE">
              Open the full research page
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </Reveal>

        <Reveal delay={0.1} className="mt-10">
          <DataState
            loading={loading}
            error={error}
            onRetry={() => {
              detail.refetch();
              alpha.refetch();
              technicals.refetch();
              prices.refetch();
            }}
            empty={!error && !loading && !detail.data}
            insufficient={Boolean(alpha.data?.insufficient_data)}
            className="chart-frame"
          >
            {detail.data && alpha.data && technicals.data && prices.data && (
              <div className="bg-surface">
                {/* Header strip */}
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
                  <div className="flex items-baseline gap-3">
                    <span className="num text-sm font-semibold">{detail.data.symbol}</span>
                    <span className="font-display text-lg">{detail.data.name}</span>
                    <span className="text-xs text-faint">{detail.data.sector ?? "-"}</span>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <span className="num text-lg font-medium">
                      {fmtPrice(detail.data.quote.last_price)}
                    </span>
                    <span
                      className={
                        (detail.data.quote.change_pct ?? 0) >= 0
                          ? "num text-xs text-band-positive"
                          : "num text-xs text-band-weak"
                      }
                    >
                      {fmtSignedPct(detail.data.quote.change_pct)}
                    </span>
                    <span className="num text-xs text-faint">
                      {fmtMarketCap(detail.data.market_cap)}
                    </span>
                  </div>
                </div>

                <div className="grid lg:grid-cols-12">
                  {/* Alpha + technical positioning */}
                  <div className="space-y-4 border-b border-line p-5 lg:col-span-4 lg:border-b-0 lg:border-r">
                    <ScoreBlock
                      score={alpha.data.composite}
                      label="Alpha Score"
                      metric="alpha"
                      size="md"
                    />
                    <div className="num grid grid-cols-3 gap-px bg-line text-xs">
                      <MiniCell k="Fund" v={String(alpha.data.fundamental ?? "-")} />
                      <MiniCell k="Technical" v={String(alpha.data.technical ?? "-")} />
                      <MiniCell k="Sentiment" v={String(alpha.data.sentiment ?? "-")} />
                    </div>
                    <div>
                      <p className="label-caps">Valuation (P/E)</p>
                      <p className="num mt-1 text-sm font-medium">
                        {alpha.data.value_signal
                          ? `${alpha.data.value_signal.status?.replace("_", " ") ?? "-"} · ${fmtSignedPct(alpha.data.value_signal.margin_pct)}`
                          : "-"}
                      </p>
                    </div>
                  </div>

                  {/* Chart */}
                  <div className="border-b border-line p-5 lg:col-span-5 lg:border-b-0 lg:border-r">
                    <p className="label-caps mb-2">Price · 6M daily</p>
                    <PriceChart bars={prices.data.items} height={240} />
                  </div>

                  {/* Technical positioning */}
                  <div className="p-5 lg:col-span-3">
                    <p className="label-caps">Technical positioning</p>
                    <p className="mt-1 font-display text-xl font-semibold">
                      {technicalVerdictWord(technicals.data.score)}
                    </p>
                    <p className="num text-xs text-muted">
                      {technicals.data.score ?? "-"} / 100
                    </p>
                    <div className="num mt-4 space-y-1 text-xs">
                      <Row k="Trend" v={technicals.data.components.trend} />
                      <Row k="Momentum" v={technicals.data.components.momentum} />
                      <Row k="Reversion" v={technicals.data.components.reversion} />
                    </div>
                    <p className="mt-4 text-xs leading-relaxed text-faint">
                      Heuristic indicator read, not a predictive model.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </DataState>
        </Reveal>
      </div>
    </section>
  );
}

function technicalVerdictWord(score: number | null): string {
  if (score == null) return "-";
  if (score >= 80) return "Strongly bullish";
  if (score >= 60) return "Bullish";
  if (score >= 40) return "Neutral";
  if (score >= 20) return "Bearish";
  return "Strongly bearish";
}

function MiniCell({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-surface px-2 py-2 text-center">
      <p className="text-xs font-medium uppercase tracking-wide text-faint">{k}</p>
      <p className="num mt-0.5 font-medium">{v}</p>
    </div>
  );
}

function Row({ k, v }: { k: string; v: number | null }) {
  return (
    <div className="flex justify-between">
      <span className="font-medium text-faint">{k}</span>
      <span className="font-medium">{v != null ? v.toFixed(1) : "-"}</span>
    </div>
  );
}
