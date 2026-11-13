import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * CollapsibleSection: the stock research page's section shell.
 * The header row (kicker, title) is always visible and is the toggle; when
 * collapsed, an optional one-line `summary` states the section's key
 * conclusion, computed by the owning section from real backend data. A
 * section without data passes no summary and the header simply shows nothing
 * there: conclusions are never invented.
 *
 * Content stays mounted while collapsed (hidden via CSS) so its queries keep
 * the same caching behavior and summaries stay data-backed.
 *
 * `index` is accepted for backwards compatibility and not rendered.
 */
export function CollapsibleSection({
  id,
  kicker,
  title,
  summary,
  aside,
  defaultOpen = false,
  children,
  className,
}: {
  id: string;
  index?: string;
  kicker?: string;
  title: string;
  summary?: string | null;
  aside?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  const contentId = `${id}-content`;

  return (
    <section id={id} className={cn("scroll-mt-28 border-b border-line", className)}>
      <div className="@container px-4 py-10 md:px-6">
        <div className={cn("border-b border-line pb-4", open && "mb-6")}>
          <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              aria-controls={contentId}
              className="group min-w-0 flex-1 text-left"
            >
              {kicker && <p className="label-caps mb-1.5">{kicker}</p>}
              <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-display text-2xl font-semibold tracking-[-0.01em] md:text-[26px]">
                  {title}
                </span>
                <ChevronDown
                  aria-hidden
                  className={cn(
                    "size-4 shrink-0 self-center text-faint transition-transform group-hover:text-foreground",
                    open && "rotate-180",
                  )}
                />
                {!open && summary && (
                  <span className="num w-full text-xs text-muted md:ml-1 md:inline md:w-auto">
                    {summary}
                  </span>
                )}
              </span>
            </button>
            {aside && open && <div className="shrink-0">{aside}</div>}
          </div>
        </div>

        {/* Hidden, not unmounted: queries stay warm and summaries stay real. */}
        <div id={contentId} hidden={!open}>
          {children}
        </div>
      </div>
    </section>
  );
}
