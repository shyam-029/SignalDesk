import * as React from "react";
import { ChevronDown } from "lucide-react";
import { motion } from "framer-motion";

import { cn } from "@/lib/utils";

/**
 * CollapsibleSection: the stock research page's section shell (Part D).
 * The header row (index, kicker, title) is always visible and is the toggle;
 * when collapsed, an optional one-line `summary` states the section's key
 * conclusion, computed by the owning section from real backend data. A
 * section without data passes no summary and the header simply shows nothing
 * there: conclusions are never invented.
 *
 * Content stays mounted while collapsed (hidden via CSS) so its queries keep
 * the same caching behavior as before and summaries stay data-backed.
 */
export function CollapsibleSection({
  id,
  index,
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
    <section id={id} className={cn("border-b border-line", className)}>
      <div className="mx-auto max-w-6xl px-4 py-12 md:px-6">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="mb-6 border-b border-line pb-4"
        >
          <div className="flex items-start justify-between gap-4">
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              aria-controls={contentId}
              className="group flex min-w-0 flex-1 items-baseline gap-4 text-left"
            >
              {index && <span className="num shrink-0 text-xs text-faint">{index}</span>}
              <span className="min-w-0">
                {kicker && <p className="label-caps mb-1">{kicker}</p>}
                <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-display text-2xl font-semibold tracking-[-0.01em] md:text-[28px]">
                    {title}
                  </span>
                  <ChevronDown
                    aria-hidden
                    className={cn(
                      "size-4 shrink-0 self-center text-faint transition-transform",
                      open && "rotate-180",
                    )}
                  />
                  {!open && summary && (
                    <span className="num w-full text-xs text-muted md:ml-1 md:inline md:w-auto">
                      {summary}
                    </span>
                  )}
                </span>
              </span>
            </button>
            {aside && <div className="shrink-0 pt-1">{aside}</div>}
          </div>
        </motion.div>

        {/* Hidden, not unmounted: queries stay warm and summaries stay real. */}
        <div id={contentId} hidden={!open}>
          {children}
        </div>
      </div>
    </section>
  );
}
