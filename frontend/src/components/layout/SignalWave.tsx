import { cn } from "@/lib/utils";

// One and a half periods of a sine, sampled once. The same wave is the
// product's recurring mark: the logo glyph, the page loader, and (in its
// vertical form) the scroll rail.
const W = 56;
const H = 24;
const PATH = `M${Array.from({ length: 57 }, (_, i) => {
  const t = i / 56;
  const x = 2 + (W - 4) * t;
  const y = H / 2 - (H / 2 - 3) * Math.sin(2 * Math.PI * 1.5 * t);
  return `${x.toFixed(2)},${y.toFixed(2)}`;
}).join(" L")}`;

/**
 * SignalWave: the SignalDesk mark. Inherits its color from `currentColor`.
 * With `drawing`, the line draws itself on a loop (used while a page loads).
 */
export function SignalWave({ className, drawing = false }: { className?: string; drawing?: boolean }) {
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      aria-hidden
      className={cn(drawing && "wave-draw", className)}
      fill="none"
    >
      <path
        d={PATH}
        pathLength={1}
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
