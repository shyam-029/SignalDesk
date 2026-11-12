import { cn } from "@/lib/utils";

// Monogram stock mark: a neutral square tile with the company's initials.
// Computed entirely from the symbol/name, so it ships zero remote requests
// and never breaks. Deliberately colorless: a row of rainbow discs made the
// tables look like an app launcher instead of a research list.

function initials(name: string | undefined, symbol: string): string {
  if (name) {
    const words = name
      .split(/\s+/)
      .filter((w) => !["Limited", "Ltd", "Industries"].includes(w));
    const letters = words.slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "");
    const joined = letters.join("");
    if (joined.length >= 2) return joined;
  }
  return symbol.replace(/\.NS$/, "").slice(0, 2).toUpperCase();
}

export function StockLogo({
  symbol,
  name,
  size = "md",
  className,
}: {
  symbol: string;
  name?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const dims =
    size === "lg" ? "size-11 text-base" : size === "sm" ? "size-6 text-[10px]" : "size-9 text-sm";
  return (
    <span
      aria-hidden
      className={cn(
        "num inline-flex shrink-0 items-center justify-center rounded-[3px] border border-rule bg-surface-2 font-semibold tracking-tight text-muted",
        dims,
        className,
      )}
    >
      {initials(name ?? undefined, symbol)}
    </span>
  );
}
