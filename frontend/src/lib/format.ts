// Centralized formatters: currency, percentages, ratios, scores, dates,
// changes, and large numbers (Indian lakh/crore). All numeric text in the UI
// flows through these so figures render consistently.

const INR = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const INR0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function fmtPrice(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `₹${INR.format(value)}`;
}

/** Indian compact notation: 1,500 Cr, 9.42 Cr, 24 L, 9,412. */
export function fmtCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  const abs = Math.abs(value);
  if (abs >= 1e7) return `${fmtScaled(value / 1e7)} Cr`;
  if (abs >= 1e5) return `${fmtScaled(value / 1e5)} L`;
  if (abs >= 1e3) return INR0.format(value);
  return String(value);
}

/** Scaled magnitudes: thousands-grouped above 100, two decimals trimmed below. */
function fmtScaled(n: number): string {
  if (n >= 100) return INR0.format(Math.round(n));
  return trimDecimals(n);
}

function trimDecimals(n: number): string {
  const rounded = n.toFixed(2);
  return rounded.replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
}

/** Market cap in rupees, rendered as ₹X Cr / ₹X L. */
export function fmtMarketCap(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  if (Math.abs(value) >= 1e7) return `₹${fmtScaled(value / 1e7)} Cr`;
  return `₹${fmtCompact(value)}`;
}

export function fmtPct(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${value.toFixed(digits)}%`;
}

/** Signed percent: -4.30% / +1.48% (null-safe). */
export function fmtSignedPct(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

/** Signed absolute amount: +1.50 / -2.10. */
export function fmtSigned(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}`;
}

export function fmtRatio(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${value.toFixed(digits)}x`;
}

export function fmtScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return String(Math.round(value));
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Relative time for news: "2 h ago", "3 d ago". */
export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diffMs = Date.now() - d.getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} d ago`;
  return fmtDate(iso);
}

/** Daily change as "+1.50 (+1.48%)" or "-". */
export function fmtChange(
  changeAbs: number | null | undefined,
  changePct: number | null | undefined,
): string {
  if (changeAbs == null && changePct == null) return "-";
  return `${fmtSigned(changeAbs)} (${fmtSignedPct(changePct)})`;
}

/** Volume as 12.4 L shares. */
export function fmtVolume(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return fmtCompact(value);
}
