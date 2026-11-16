import { rankPosition } from "@/components/fund/fundFormat";
import { cn } from "@/lib/utils";

/**
 * RankBar: a fund's place in its category by one-year return, as "Top 12%"
 * over a thin bar (full = first place). Small categories show the plain
 * "3 of 4" because a percentage of four funds says little. Missing is "-".
 */
export function RankBar({
  rank,
  size,
  align = "right",
  className,
}: {
  rank: number | null | undefined;
  size: number | null | undefined;
  align?: "left" | "right";
  className?: string;
}) {
  if (rank == null || size == null) {
    return <span className={cn("num text-xs text-faint", className)}>-</span>;
  }
  const pos = rankPosition(rank, size);
  const plain = `${rank} of ${size}`;
  if (!pos) return <span className={cn("num text-xs text-muted", className)}>{plain}</span>;
  const half = pos.topPct <= 50;
  return (
    <span
      className={cn("inline-block w-20", align === "right" && "text-right", className)}
      title={`${plain} in its category, by one-year return`}
    >
      <span className="num block text-xs font-medium">
        {half ? `Top ${pos.topPct}%` : `Bottom ${Math.max(1, 101 - pos.topPct)}%`}
      </span>
      <span className="mt-1 block h-1 bg-line" aria-hidden>
        <span
          className="block h-1"
          style={{ width: `${pos.fill}%`, background: half ? "var(--up)" : "var(--faint)" }}
        />
      </span>
    </span>
  );
}
