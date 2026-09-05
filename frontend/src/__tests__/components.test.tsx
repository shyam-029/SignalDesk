import { describe, expect, it, vi } from "vitest";
import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { DataState } from "@/components/data/DataState";
import { InfoContent, InfoDot } from "@/components/data/InfoDot";
import { ScoreBlock } from "@/components/data/ScoreBlock";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";
import { METRIC_INFO } from "@/lib/metrics";

function renderWithProviders(ui: React.ReactElement) {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
}

describe("DataState", () => {
  it("renders children when ready", () => {
    renderWithProviders(
      <DataState>
        <p>ready content</p>
      </DataState>,
    );
    expect(screen.getByText("ready content")).toBeInTheDocument();
  });

  it("shows the default skeleton while loading", () => {
    const { container } = renderWithProviders(
      <DataState loading>
        <p>hidden</p>
      </DataState>,
    );
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
    expect(screen.queryByText("hidden")).not.toBeInTheDocument();
  });

  it("shows unknown-symbol state for 404 ApiErrors", () => {
    renderWithProviders(
      <DataState error={new ApiError(404, "RESOURCE_NOT_FOUND", "Stock NOPE.NS not found")}>
        <p>hidden</p>
      </DataState>,
    );
    expect(screen.getByText("Unknown symbol")).toBeInTheDocument();
    expect(screen.queryByText("hidden")).not.toBeInTheDocument();
  });

  it("shows API-unreachable state for network errors and offers retry", async () => {
    const onRetry = vi.fn();
    renderWithProviders(
      <DataState error={new ApiError(0, "NETWORK_ERROR", "Cannot reach the SignalDesk API.")} onRetry={onRetry}>
        <p>hidden</p>
      </DataState>,
    );
    expect(screen.getByText("API unreachable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders insufficient-data state without estimating values", () => {
    renderWithProviders(
      <DataState insufficient>
        <p>hidden</p>
      </DataState>,
    );
    expect(screen.getByText("Insufficient data")).toBeInTheDocument();
    expect(screen.queryByText("hidden")).not.toBeInTheDocument();
  });

  it("renders empty state with custom copy", () => {
    renderWithProviders(
      <DataState empty emptyTitle="No matches" emptyMessage="Loosen the filters.">
        <p>hidden</p>
      </DataState>,
    );
    expect(screen.getByText("No matches")).toBeInTheDocument();
  });
});

describe("InfoDot", () => {
  it("renders an accessible trigger carrying the metric label", () => {
    renderWithProviders(<InfoDot metric="pe" />);
    expect(screen.getByRole("button", { name: /about P\/E/i })).toBeInTheDocument();
  });

  it("exposes the methodology popover body with definition + methodology", () => {
    renderWithProviders(<InfoContent info={METRIC_INFO.pe} />);
    expect(screen.getByText("P/E")).toBeInTheDocument();
    expect(screen.getByText("Methodology")).toBeInTheDocument();
    expect(screen.getByText(/median of same-industry peers/i)).toBeInTheDocument();
  });

  it("omits the methodology block for entries without one", () => {
    renderWithProviders(<InfoContent info={METRIC_INFO.market_cap} />);
    expect(screen.getByText("Market cap")).toBeInTheDocument();
    expect(screen.queryByText("Methodology")).not.toBeInTheDocument();
  });
});

describe("ScoreBlock", () => {
  it("renders the score with its band word and color class", () => {
    const { container } = renderWithProviders(
      <ScoreBlock score={59} label="Alpha Score" metric="alpha" />,
    );
    expect(screen.getByText(/Moderate/)).toBeInTheDocument();
    expect(container.querySelector(".text-band-moderate")).not.toBeNull();
    expect(container.textContent).toContain("/100");
  });

  it("renders the unavailable state for null scores", () => {
    renderWithProviders(<ScoreBlock score={null} label="Technical Score" />);
    expect(screen.getByText(/Score unavailable/)).toBeInTheDocument();
  });
});
