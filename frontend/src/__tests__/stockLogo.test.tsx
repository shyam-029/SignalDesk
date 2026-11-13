import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StockLogo } from "@/components/stock/StockLogo";
import { LOGO_SYMBOLS } from "@/lib/logoIndex";
import { logoFile, logoUrl } from "@/lib/logos";

describe("company logos", () => {
  it("maps symbols to the file names build_logos.py writes", () => {
    expect(logoFile("RELIANCE.NS")).toBe("RELIANCE");
    expect(logoFile("m&m")).toBe("M_M");
    expect(logoFile("BAJAJ-AUTO")).toBe("BAJAJ-AUTO");
  });

  it("only returns a URL for symbols that have a file", () => {
    const known = LOGO_SYMBOLS[0];
    expect(logoUrl(known)).toBe(`/logos/${logoFile(known)}.webp`);
    expect(logoUrl(`${known}.NS`)).toBe(`/logos/${logoFile(known)}.webp`);
    expect(logoUrl("NOT-A-LISTED-STOCK")).toBeNull();
  });

  it("shows the logo when there is one, initials otherwise", () => {
    const known = LOGO_SYMBOLS[0];
    const { container: withLogo } = render(<StockLogo symbol={known} name="Some Company" />);
    expect(withLogo.querySelector("img")?.getAttribute("src")).toBe(logoUrl(known));

    const { container: without } = render(<StockLogo symbol="NOPE" name="Nope Holdings" />);
    expect(without.querySelector("img")).toBeNull();
    expect(without.textContent).toBe("NH");
  });

  it("falls back to initials when the image fails to load", () => {
    const known = LOGO_SYMBOLS[0];
    const { container } = render(<StockLogo symbol={known} name="Acme Widgets" />);
    fireEvent.error(container.querySelector("img")!);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe("AW");
  });
});
