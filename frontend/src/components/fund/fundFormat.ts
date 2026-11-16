// Small shared helpers for the fund and ETF pages. Pure functions only.

const INR = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function fmtRupees(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "-" : `₹${INR.format(Math.round(value))}`;
}

/** Badge text for a fund's kind; plain actively managed open funds get none. */
export function kindLabel(kind: string | null | undefined): string | null {
  switch (kind) {
    case "index":
      return "Index";
    case "etf":
      return "ETF";
    case "fof":
      return "Fund of funds";
    case "closed":
      return "Closed-ended";
    default:
      return null;
  }
}

/**
 * Where a rank sits in its category: 1 of 200 is the top 1%, 200 of 200 the
 * bottom. `fill` is the share of the category at or below this fund (for a
 * bar). Null when the category is too small for a percentage to mean much.
 */
export function rankPosition(
  rank: number | null | undefined,
  size: number | null | undefined,
): { topPct: number; fill: number } | null {
  if (rank == null || size == null || size < 5 || rank < 1 || rank > size) return null;
  return {
    topPct: Math.max(1, Math.ceil((rank / size) * 100)),
    fill: ((size - rank + 1) / size) * 100,
  };
}

/**
 * What 10,000 became. `pct` is a plain return for windows under a year and a
 * yearly rate (CAGR) for `years` of one or more.
 */
export function grewTo(pct: number | null | undefined, years: number, start = 10_000): number | null {
  if (pct == null) return null;
  const rate = pct / 100;
  if (rate <= -1) return 0;
  return years >= 1 ? start * Math.pow(1 + rate, years) : start * (1 + rate);
}

/** Whole years and months between two ISO dates, in words. */
export function spanInWords(fromIso: string, toIso: string): string {
  const a = new Date(fromIso);
  const b = new Date(toIso);
  let months = (b.getFullYear() - a.getFullYear()) * 12 + (b.getMonth() - a.getMonth());
  if (b.getDate() < a.getDate()) months -= 1;
  if (months < 1) {
    const days = Math.max(1, Math.round((b.getTime() - a.getTime()) / 86_400_000));
    return `${days} day${days === 1 ? "" : "s"}`;
  }
  const y = Math.floor(months / 12);
  const m = months % 12;
  const parts: string[] = [];
  if (y) parts.push(`${y} year${y === 1 ? "" : "s"}`);
  if (m) parts.push(`${m} month${m === 1 ? "" : "s"}`);
  return parts.join(" ");
}
