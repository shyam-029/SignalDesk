import * as React from "react";
import { motion, type Variants } from "framer-motion";

/** Shared motion tokens: one reduced-motion hook + the standard ease curve
 *  so every reveal in the product behaves the same way. */
export function useReducedMotionSafe(): boolean {
  const reduced = React.useSyncExternalStore(
    () => () => {},
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
  return reduced;
}

const EASE = [0.22, 1, 0.36, 1] as const;

/** Standard section entrance: small rise + fade, once, on view. Honors
 *  prefers-reduced-motion by rendering visible without any transform. */
export function Reveal({
  children,
  delay = 0,
  className,
  y = 16,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
  y?: number;
}) {
  const reduced = useReducedMotionSafe();
  return (
    <motion.div
      initial={reduced ? { opacity: 1 } : { opacity: 0, y }}
      whileInView={reduced ? { opacity: 1 } : { opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={reduced ? { duration: 0 } : { duration: 0.55, delay, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Staggered children container (see `item` for the child variant). */
export const staggerParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: EASE },
  },
};
