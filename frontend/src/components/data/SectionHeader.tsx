import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * SectionHeader: a plain section opener. A small caps kicker, a serif title,
 * an optional right-hand control, and one hairline rule. It does not animate:
 * headings that fade in on scroll read as decoration, not as research.
 *
 * `index` is accepted for backwards compatibility and intentionally not
 * rendered (the hanging "02" numerals pushed titles off the content edge).
 */
export function SectionHeader({
  title,
  kicker,
  aside,
  className,
}: {
  index?: string;
  title: string;
  kicker?: string;
  aside?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-6 border-b border-line pb-4", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
        <div>
          {kicker && <p className="label-caps mb-1.5">{kicker}</p>}
          <h2 className="font-display text-2xl font-semibold tracking-[-0.01em] md:text-[26px]">
            {title}
          </h2>
        </div>
        {aside && <div className="shrink-0">{aside}</div>}
      </div>
    </div>
  );
}
