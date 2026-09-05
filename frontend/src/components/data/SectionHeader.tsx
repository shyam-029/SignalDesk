import * as React from "react";
import { motion } from "framer-motion";

import { cn } from "@/lib/utils";

/**
 * SectionHeader: editorial section opener: optional index ("02"), a serif
 * title, an optional kicker, and a hairline rule. Sections are separated by
 * rules and whitespace, not by wrapping everything in cards.
 */
export function SectionHeader({
  index,
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
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={cn("mb-6 border-b border-line pb-4", className)}
    >
      <div className="flex items-baseline justify-between gap-4">
        <div className="flex items-baseline gap-4">
          {index && <span className="num text-xs text-faint">{index}</span>}
          <div>
            {kicker && <p className="label-caps mb-1">{kicker}</p>}
            <h2 className="font-display text-2xl font-semibold tracking-[-0.01em] md:text-[28px]">
              {title}
            </h2>
          </div>
        </div>
        {aside && <div className="shrink-0">{aside}</div>}
      </div>
    </motion.div>
  );
}
