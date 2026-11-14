import { describe, expect, it } from "vitest";

import { expectationsSummary } from "@/components/stock/ExpectationsSection";
import { setupsSummary } from "@/components/stock/SetupsSection";
import type { ExpectationsResponse, SetupsResponse } from "@/lib/types";

/**
 * The collapsed-section summary lines for the edge features: data-backed,
 * and absent (not invented) when the backend has no answer.
 */

function expectations(over: Partial<ExpectationsResponse> = {}): ExpectationsResponse {
  return {
    symbol: "TRENT.NS",
    status: "ok",
    reason: null,
    market_value: 1e12,
    earnings: 1e10,
    earnings_basis: "last_4_quarters",
    earnings_period_end: "2026-09-30",
    pe: 100,
    years: 10,
    terminal_growth_pct: 6,
    implied: [
      { discount_rate_pct: 11, growth_pct: 25, bound: null },
      { discount_rate_pct: 12, growth_pct: 27.9, bound: null },
      { discount_rate_pct: 13, growth_pct: 30.7, bound: null },
    ],
    own: {
      years: 3,
      from_year_end: "2023-03-31",
      to_year_end: "2026-03-31",
      earnings_growth_pct: 57,
      revenue_growth_pct: 34.8,
    },
    base_rate_pct: 32,
    base_rate_windows: 860,
    base_rate_years: 3,
    ...over,
  };
}

describe("expectationsSummary", () => {
  it("states the growth at the 12% rate", () => {
    expect(expectationsSummary(expectations())).toBe(
      "The price assumes earnings growing about 27.9% a year for 10 years",
    );
  });

  it("says shrinking for a negative answer and nothing for a loss-maker", () => {
    const shrinking = expectations({
      implied: [{ discount_rate_pct: 12, growth_pct: -5.9, bound: null }],
    });
    expect(expectationsSummary(shrinking)).toContain("shrinking about 5.9% a year");
    expect(
      expectationsSummary(expectations({ status: "not_meaningful", reason: "loss_making" })),
    ).toBeNull();
  });
});

describe("setupsSummary", () => {
  const base: SetupsResponse = {
    symbol: "TRENT.NS",
    status: "ok",
    asof: "2026-11-13",
    today: { strength: 11, steadiness: 16, high_rank: 20, year_return_pct: -30, from_high_pct: -31.5 },
    horizons: [
      { horizon: "3m", similar: { n: 200, median: -2.1 }, all_samples: { n: 75000, median: 2.5 } },
      { horizon: "12m", similar: { n: 200, median: 21.1 }, all_samples: { n: 67000, median: 12.9 } },
    ],
    samples: 79389,
    shares: 1000,
    sample_from: "2017-11-30",
    sample_to: "2026-11-13",
    neighbours: 200,
  };

  it("leads with the 12-month median of the similar cases", () => {
    expect(setupsSummary(base)).toBe(
      "In 200 similar past setups, the median 12-month move was +21.1%",
    );
  });

  it("shows nothing before the weekly pass has run", () => {
    expect(setupsSummary({ ...base, status: "none", horizons: [] })).toBeNull();
  });
});
