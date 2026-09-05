import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScoreBlock } from "@/components/data/ScoreBlock";
import { cn } from "@/lib/utils";

/**
 * Hero: establishes the product as a research instrument. The visual is
 * real SignalDesk structure (a price line drawing in, mono metrics, an Alpha
 * object) rather than a laptop mockup or decorative gradients.
 */
export function Hero({ sparkline }: { sparkline: number[] | null }) {
  return (
    <section className="relative border-b border-line">
      {/* Depth wash: a faint gold pool behind the signal card. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(620px 340px at 78% 30%, color-mix(in srgb, var(--cobalt) 7%, transparent), transparent 72%)",
        }}
      />
      <div className="relative mx-auto max-w-6xl px-4 pb-16 pt-16 md:px-6 md:pb-24 md:pt-24">
        <div className="grid items-center gap-12 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5 }}
              className="label-caps mb-5"
            >
              Equity research · India
            </motion.p>
            <motion.h1
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              className="font-display text-4xl font-bold leading-[1.12] tracking-[-0.015em] md:text-[56px] md:leading-[1.08]"
            >
              The market doesn't need more noise.
              <br />
              <span className="text-cobalt dark:text-cobalt-strong">
                It needs better research.
              </span>
            </motion.h1>
            <motion.p
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.15 }}
              className="mt-6 max-w-xl text-base leading-relaxed text-muted md:text-lg"
            >
              SignalDesk reads the same public numbers everyone else sees, then does the
              work of turning them into <span className="hi">structured, explainable research</span>:
              fundamentals, relative valuation, technical positioning, and news sentiment,
              combined into <span className="hi">one clear signal</span>.
            </motion.p>
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.28 }}
              className="mt-8 flex flex-wrap items-center gap-3"
            >
              <Button asChild size="lg" className="gap-2">
                <Link to="/markets">
                  Explore the research
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <a href="#how-it-works">See how it works</a>
              </Button>
            </motion.div>
          </div>

          {/* Hero visual: the analytical object itself. */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className="lg:col-span-5"
          >
            <div className="glass border-cobalt/25">
              <div className="flex items-center justify-between border-b border-line px-4 py-3">
                <div>
                  <p className="label-caps">Signal · Reliance Industries</p>
                  <p className="num mt-0.5 text-xs text-muted">NSE · RELIANCE</p>
                </div>
                <span className="label-caps">Illustrative</span>
              </div>
              {sparkline && sparkline.length > 1 && (
                <Sparkline points={sparkline} />
              )}
              <div className="border-t border-line p-4">
                <ScoreBlock score={59} label="Alpha Score" metric="alpha" size="md" flat />
              </div>
              <div className="num grid grid-cols-3 gap-px border-t border-line bg-line text-xs">
                <Cell k="Fundamental" v="98" dot="bg-accent-jade" />
                <Cell k="Technical" v="27" dot="bg-accent-coral" />
                <Cell k="Sentiment" v="39" dot="bg-accent-teal" />
              </div>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-faint">
              Composite score = 40% fundamental + 30% technical + 30% sentiment. Valuation is
              assessed separately.
            </p>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

function Cell({ k, v, dot }: { k: string; v: string; dot?: string }) {
  return (
    <div className="bg-surface px-3 py-2.5 text-center">
      <p className="flex items-center justify-center gap-1.5 text-xs font-medium uppercase tracking-wide text-faint">
        {dot && <span className={cn("inline-block size-1.5 rounded-full", dot)} aria-hidden />}
        {k}
      </p>
      <p className="num mt-0.5 text-sm font-medium">{v}</p>
    </div>
  );
}

function Sparkline({ points }: { points: number[] }) {
  const W = 420;
  const H = 110;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = W / (points.length - 1);
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(H - 8 - ((p - min) / range) * (H - 20)).toFixed(1)}`)
    .join(" ");
  const up = points.at(-1)! >= points[0];

  return (
    <div className="px-4 pt-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-24 w-full" role="img" aria-label="Price path">
        <motion.path
          d={path}
          fill="none"
          stroke={up ? "var(--band-positive)" : "var(--band-weak)"}
          strokeWidth="1.8"
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.6, ease: "easeOut", delay: 0.5 }}
        />
      </svg>
      <p className="num mb-1 text-right text-xs text-faint">6-month close · daily bars</p>
    </div>
  );
}
