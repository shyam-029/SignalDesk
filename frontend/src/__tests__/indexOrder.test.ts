import { describe, expect, it } from "vitest";

import { orderIndexes } from "@/lib/indexOrder";

describe("market index order", () => {
  it("puts NIFTY 50 first and VIX last, unknown symbols after", () => {
    const api = ["^BSESN", "^CNXIT", "^CNXPHARMA", "^CRSLDX", "^INDIAVIX", "^NSEBANK", "^NSEI", "^NEW", "^NSEMDCP50"].map(
      (symbol) => ({ symbol }),
    );
    expect(orderIndexes(api).map((x) => x.symbol)).toEqual([
      "^NSEI",
      "^BSESN",
      "^NSEBANK",
      "^CNXIT",
      "^CNXPHARMA",
      "^NSEMDCP50",
      "^CRSLDX",
      "^INDIAVIX",
      "^NEW",
    ]);
  });
});
