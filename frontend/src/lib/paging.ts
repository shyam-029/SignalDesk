// Screener paging helpers (work list item 14b).

export const SCREENER_PAGE_SIZE = 10;

/** "Showing 11-20 of 312" for a 1-based page. */
export function pageRangeLabel(page: number, pageSize: number, total: number): string {
  if (total <= 0) return "No matches";
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(total, page * pageSize);
  return `Showing ${first}-${last} of ${total}`;
}

/** Number of pages for `total` rows (at least 1, so "Page 1 of 1" reads well). */
export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}
