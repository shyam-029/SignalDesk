import * as React from "react";

import {
  usePrices,
  PRICE_RANGES,
  PRICE_RANGE_LABELS,
  type PriceRange,
} from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { SectionHeader } from "@/components/data/SectionHeader";
import { PriceChart } from "@/components/chart/PriceChart";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

/**
 * PriceSection: the primary price chart (real Lightweight Charts), kept
 * open on the research page (Part D keeps the chart visible; the technical
 * positioning panel and indicator series live in the collapsible
 * Technicals section). The verdict-free chart shows raw market data only.
 */
export function PriceSection({ symbol }: { symbol: string }) {
  const [range, setRange] = React.useState<PriceRange>("6mo");
  const prices = usePrices(symbol, range);

  return (
    <section id="price" className="section-alt border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
        <SectionHeader
          index="03"
          kicker="Price"
          title="Price history"
          aside={
            <Tabs value={range} onValueChange={(v) => setRange(v as PriceRange)}>
              <TabsList>
                {PRICE_RANGES.map((r) => (
                  <TabsTrigger key={r} value={r}>
                    {PRICE_RANGE_LABELS[r]}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          }
        />

        <div className="border border-line bg-surface p-5">
          <div className="mb-3 flex items-center justify-between">
            <p className="label-caps">Daily closes · OHLC</p>
          </div>
          <DataState
            loading={prices.isLoading}
            error={prices.error}
            onRetry={prices.refetch}
            empty={Boolean(prices.data) && (prices.data?.items.length ?? 0) === 0}
            emptyTitle="No price history"
            emptyMessage="No daily bars are stored for this window yet."
            compact
          >
            {prices.data && prices.data.items.length > 0 && (
              <>
                <PriceChart bars={prices.data.items} height={360} />
                <p className="num mt-2 text-xs text-faint">
                  {prices.data.items.length} daily bars · {range} window · resample 1d
                </p>
              </>
            )}
          </DataState>
        </div>
      </div>
    </section>
  );
}
