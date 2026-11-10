import { describe, expect, it } from "vitest";

import { SCREENER_PAGE_SIZE, pageCount, pageRangeLabel } from "@/lib/paging";

describe("screener paging", () => {
  it("shows ten rows per page", () => {
    expect(SCREENER_PAGE_SIZE).toBe(10);
  });

  it("labels the visible range, clamping the last page", () => {
    expect(pageRangeLabel(1, 10, 312)).toBe("Showing 1-10 of 312");
    expect(pageRangeLabel(2, 10, 312)).toBe("Showing 11-20 of 312");
    expect(pageRangeLabel(32, 10, 312)).toBe("Showing 311-312 of 312");
    expect(pageRangeLabel(1, 10, 0)).toBe("No matches");
  });

  it("counts pages, never fewer than one", () => {
    expect(pageCount(312, 10)).toBe(32);
    expect(pageCount(10, 10)).toBe(1);
    expect(pageCount(0, 10)).toBe(1);
  });
});
