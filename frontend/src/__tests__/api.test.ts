import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, apiGet } from "@/lib/api";

/**
 * The API client is exercised against a stubbed fetch: success, error-envelope
 * parsing, network failure, and each endpoint's URL shape.
 */

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "ok" }));
    const data = await apiGet<{ status: string }>("/health");
    expect(data.status).toBe("ok");
  });

  it("parses the backend error envelope into ApiError", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, {
        error: {
          code: "RESOURCE_NOT_FOUND",
          message: "Stock NOPE.NS not found",
          detail: { symbol: "NOPE.NS" },
          request_id: "abc123",
        },
      }),
    );

    const err = await apiGet("/stocks/NOPE").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).code).toBe("RESOURCE_NOT_FOUND");
    expect((err as ApiError).isNotFound).toBe(true);
    expect((err as ApiError).message).toContain("NOPE.NS");
  });

  it("maps non-JSON error bodies to a usable ApiError", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
    });
    const err = await apiGet("/stocks/X").catch((e) => e);
    expect((err as ApiError).code).toBe("HTTP_500");
  });

  it("converts network failure into NETWORK_ERROR", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const err = await apiGet("/stocks").catch((e) => e);
    expect((err as ApiError).status).toBe(0);
    expect((err as ApiError).code).toBe("NETWORK_ERROR");
  });

  it("posts JSON bodies for /explain", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        symbol: "RELIANCE.NS",
        question_type: "alpha",
        explanation: "Generated.",
      }),
    );
    const data = await api.explain("RELIANCE", "alpha");
    expect(data.explanation).toBe("Generated.");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/stocks/RELIANCE/explain");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      question_type: "alpha",
    });
  });

  it("builds correct screener query strings", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, page: 1, limit: 200 }));
    await api.screener({ status: "undervalued", minProfitability: 60, page: 1, limit: 200 });
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/screener?");
    expect(url).toContain("status=undervalued");
    expect(url).toContain("min_profitability=60");
  });

  it("encodes symbols in price/detail paths", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [] }));
    await api.stockDetail("M&M");
    await api.prices("RELIANCE", "1mo");
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls[0]).toContain("/stocks/M%26M");
    expect(urls[1]).toContain("/stocks/RELIANCE/prices?range=1mo");
  });
});
