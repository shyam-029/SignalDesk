import { cn } from "@/lib/utils";

// Monogram stock mark: a colored disc with the company's initials. Computed
// entirely from the symbol/name (deterministic hash into a small palette of
// theme tokens), so it ships zero remote requests and never breaks.
const PALETTE = [
  "--accent-jade",
  "--accent-teal",
  "--accent-coral",
  "--accent-amber",
  "--cobalt",
];

function hashCode(value: string): number {
  let h = 0;
  for (let i = 0; i < value.length; i++) {
    h = (h * 31 + value.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

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
  const colorVar = PALETTE[hashCode(symbol) % PALETTE.length];
  const dims =
    size === "lg" ? "size-12 text-lg" : size === "sm" ? "size-6 text-[10px]" : "size-9 text-sm";
  return (
    <span
      aria-hidden
      className={cn(
        "num inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white",
        dims,
        className,
      )}
      style={{ backgroundColor: `color-mix(in srgb, var(${colorVar}) 82%, black 6%)` }}
    >
      {initials(name ?? undefined, symbol)}
    </span>
  );
}
