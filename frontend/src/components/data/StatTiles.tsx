import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * StatTiles: a row of headline figures in the hairline-grid style used across
 * the research pages. Each tile is a label, one figure and an optional note.
 * `tone` colors the figure for a gain or a loss; the default is neutral.
 */
export interface StatTile {
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
  tone?: "up" | "down";
}

const COLS: Record<number, string> = {
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-2 sm:grid-cols-4",
  5: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5",
  6: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-6",
};

export function StatTiles({ tiles, className }: { tiles: StatTile[]; className?: string }) {
  return (
    <dl
      className={cn(
        "grid gap-px border border-line bg-line",
        COLS[tiles.length] ?? "grid-cols-2 sm:grid-cols-4",
        className,
      )}
    >
      {tiles.map((t) => (
        <div key={t.label} className="min-w-0 bg-surface p-4">
          <dt className="label-caps truncate">{t.label}</dt>
          <dd
            className={cn(
              "num mt-1 truncate text-xl font-medium",
              t.tone === "up" && "text-up",
              t.tone === "down" && "text-down",
            )}
          >
            {t.value}
          </dd>
          {t.note && <dd className="mt-0.5 text-[11px] leading-snug text-faint">{t.note}</dd>}
        </div>
      ))}
    </dl>
  );
}
