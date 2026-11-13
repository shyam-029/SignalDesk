// Company logos (2026-11-13). ops/logos/build_logos.py downloads one small
// WebP per listed company into public/logos/ and writes LOGO_SYMBOLS, the
// symbols that have one. They ship as static files with the site, so they
// cost no API call, no Worker request and no R2 read. A stock without a file
// keeps the initials badge, and the site never requests a missing logo.

import { LOGO_SYMBOLS } from "@/lib/logoIndex";

const HAVE = new Set(LOGO_SYMBOLS);

function bare(symbol: string): string {
  const s = symbol.trim().toUpperCase();
  return s.endsWith(".NS") ? s.slice(0, -3) : s;
}

/** File name stem; must match file_stem() in ops/logos/build_logos.py. */
export function logoFile(symbol: string): string {
  return bare(symbol).replace(/[^A-Z0-9-]/g, "_");
}

/** URL of the stock's logo, or null when there is none. */
export function logoUrl(symbol: string): string | null {
  return HAVE.has(bare(symbol)) ? `/logos/${logoFile(symbol)}.webp` : null;
}
