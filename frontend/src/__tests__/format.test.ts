import { describe, expect, it } from "vitest";

import {
  fmtChange,
  fmtCompact,
  fmtMarketCap,
  fmtPrice,
  fmtRatio,
  fmtRelative,
  fmtScore,
  fmtSigned,
  fmtSignedPct,
  fmtVolume,
} from "@/lib/format";

describe("formatters", () => {
  it("render null-safe em dashes everywhere", () => {
    expect(fmtPrice(null)).toBe("—");
    expect(fmtMarketCap(undefined)).toBe("—");
    expect(fmtRatio(null)).toBe("—");
    expect(fmtSignedPct(null)).toBe("—");
    expect(fmtScore(Number.NaN)).toBe("—");
  });

  it("format prices with Indian grouping", () => {
    expect(fmtPrice(1234.5)).toBe("₹1,234.50");
    expect(fmtPrice(1234567.89)).toBe("₹12,34,567.89");
  });

  it("compact Indian magnitudes", () => {
    expect(fmtCompact(15_000_000_000)).toBe("1,500 Cr");
    expect(fmtCompact(94_200_000)).toBe("9.42 Cr");
    expect(fmtCompact(2_400_000)).toBe("24 L");
    expect(fmtCompact(9412)).toBe("9,412");
    expect(fmtCompact(412)).toBe("412");
  });

  it("market caps render as ₹ Cr with Indian grouping", () => {
    expect(fmtMarketCap(1_500_000_000_000)).toBe("₹1,50,000 Cr");
  });

  it("signed helpers keep explicit signs", () => {
    expect(fmtSigned(1.5)).toBe("+1.50");
    expect(fmtSigned(-2.05)).toBe("-2.05");
    expect(fmtSignedPct(0.96)).toBe("+0.96%");
    expect(fmtSignedPct(-4.3)).toBe("-4.30%");
  });

  it("daily change combines abs + pct", () => {
    expect(fmtChange(1.5, 0.96)).toBe("+1.50 (+0.96%)");
    expect(fmtChange(null, null)).toBe("—");
  });

  it("volumes use compact shares", () => {
    expect(fmtVolume(1_200_400)).toContain("L");
    expect(fmtVolume(null)).toBe("—");
  });

  it("relative time reads naturally", () => {
    const now = Date.now();
    expect(fmtRelative(new Date(now - 30_000).toISOString())).toBe("just now");
    expect(fmtRelative(new Date(now - 3 * 60_000).toISOString())).toBe("3 min ago");
    expect(fmtRelative(new Date(now - 5 * 3_600_000).toISOString())).toBe("5 h ago");
  });
});
