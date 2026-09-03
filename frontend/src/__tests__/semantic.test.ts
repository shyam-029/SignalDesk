import { describe, expect, it } from "vitest";

import {
  scoreBand,
  technicalVerdict,
  valuationSemantics,
  sentimentSemantics,
} from "@/lib/semantic";

describe("score bands", () => {
  it("map the five approved ranges", () => {
    expect(scoreBand(82)?.key).toBe("strong");
    expect(scoreBand(80)?.key).toBe("strong");
    expect(scoreBand(79)?.key).toBe("positive");
    expect(scoreBand(60)?.key).toBe("positive");
    expect(scoreBand(59)?.key).toBe("moderate");
    expect(scoreBand(40)?.key).toBe("moderate");
    expect(scoreBand(39)?.key).toBe("weak");
    expect(scoreBand(20)?.key).toBe("weak");
    expect(scoreBand(19)?.key).toBe("veryweak");
    expect(scoreBand(0)?.key).toBe("veryweak");
  });

  it("handle unavailable scores", () => {
    expect(scoreBand(null)).toBeNull();
    expect(scoreBand(undefined)).toBeNull();
    expect(scoreBand(Number.NaN)).toBeNull();
  });

  it("carry distinct classes for text/tint/border/bar", () => {
    const band = scoreBand(82)!;
    expect(band.text).toMatch(/^text-band-/);
    expect(band.bg).toMatch(/^bg-band-/);
    expect(band.border).toMatch(/^border-band-/);
    expect(band.bar).toMatch(/^bg-band-/);
    expect(band.label).toBe("Strong");
  });
});

describe("technical verdict", () => {
  it("uses technical-evidence wording only", () => {
    expect(technicalVerdict(85)?.word).toBe("Strongly bullish");
    expect(technicalVerdict(64)?.word).toBe("Bullish");
    expect(technicalVerdict(45)?.word).toBe("Neutral");
    expect(technicalVerdict(27)?.word).toBe("Bearish");
    expect(technicalVerdict(5)?.word).toBe("Strongly bearish");
    expect(technicalVerdict(null)).toBeNull();
  });

  it("colors the verdict by band, not by day movement", () => {
    expect(technicalVerdict(27)?.band.key).toBe("weak");
    expect(technicalVerdict(85)?.band.key).toBe("strong");
  });
});

describe("valuation semantics (independent of Alpha)", () => {
  it("maps the three backend statuses", () => {
    expect(valuationSemantics("undervalued")?.headline).toBe("Cheaper than peers");
    expect(valuationSemantics("fairly_valued")?.headline).toBe("In line with peers");
    expect(valuationSemantics("overvalued")?.headline).toBe("More expensive than peers");
    expect(valuationSemantics(null)).toBeNull();
  });

  it("does not inherit Alpha banding", () => {
    // Fairly valued is NEUTRAL (moderate), regardless of a high or low Alpha.
    expect(valuationSemantics("fairly_valued")?.band.key).toBe("moderate");
  });
});

describe("sentiment semantics", () => {
  it("maps labels to semantic bands", () => {
    expect(sentimentSemantics("positive").band.key).toBe("positive");
    expect(sentimentSemantics("negative").band.key).toBe("veryweak");
    expect(sentimentSemantics("neutral").band.key).toBe("moderate");
    expect(sentimentSemantics(undefined).label).toBe("Neutral");
  });
});
