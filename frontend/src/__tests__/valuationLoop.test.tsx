import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "@/lib/api";
import { ValuationSection } from "@/components/stock/ValuationSection";
import { TooltipProvider } from "@/components/ui/tooltip";

const ok = (metric: string) => ({
  symbol: "HDFCBANK.NS", method: "relative", metric, peers: ["ICICIBANK.NS"],
  current: 2, peer_median: 2.5, margin_pct: -20, status: "undervalued", computed_at: "x",
});

afterEach(() => vi.restoreAllMocks());

describe("valuation with a metric the stock lacks", () => {
  it("asks for the missing multiple once, not in a loop", async () => {
    const calls: Record<string, number> = {};
    vi.spyOn(api, "valuation").mockImplementation(async (_s, metric) => {
      calls[metric] = (calls[metric] ?? 0) + 1;
      if (metric === "EV_EBITDA") throw new ApiError(422, "INSUFFICIENT_DATA", "Cannot compute");
      return ok(metric) as never;
    });
    vi.spyOn(api, "fundamentals").mockResolvedValue({ symbol: "HDFCBANK.NS", key_ratios: {}, updated_at: null } as never);
    vi.spyOn(api, "peers").mockRejectedValue(new ApiError(422, "NO_PEERS", "none"));
    const client = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });
    render(
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <MemoryRouter>
            <ValuationSection symbol="HDFCBANK" />
          </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(calls.PS).toBeGreaterThan(0));
    await new Promise((r) => setTimeout(r, 300));
    expect(calls.EV_EBITDA).toBe(1);

    // Selecting the missing multiple must show the "not computable" note,
    // not a skeleton that re-requests it forever.
    fireEvent.click(screen.getByRole("button", { name: /^EV\/EBITDA/ }));
    await new Promise((r) => setTimeout(r, 1500));
    expect(calls.EV_EBITDA).toBeLessThanOrEqual(2);
    expect(await screen.findByText(/lacks the inputs for this multiple/)).toBeTruthy();
  });
});
