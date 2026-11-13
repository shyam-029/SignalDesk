import * as React from "react";

import { logoUrl } from "@/lib/logos";
import { cn } from "@/lib/utils";

// Stock mark: the company's logo when one was downloaded (lib/logos.ts,
// static files shipped with the site), otherwise a neutral square tile with
// the company's initials. Logos sit on a white tile so dark marks stay
// visible in dark mode; a logo that fails to load falls back to the
// initials. Deliberately colorless fallback: a row of rainbow discs made the
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
  const src = logoUrl(symbol);
  const [failed, setFailed] = React.useState(false);
  if (src && !failed) {
    return (
      <span
        aria-hidden
        className={cn(
          "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[3px] border border-rule bg-white",
          dims,
          className,
        )}
      >
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          draggable={false}
          className="size-full object-contain"
          onError={() => setFailed(true)}
        />
      </span>
    );
  }
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
