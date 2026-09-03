import { BAND_EXAMPLES } from "@/lib/semantic";
import { ScoreBlock } from "@/components/data/ScoreBlock";
import { Reveal } from "@/components/motion/Reveal";
import { cn } from "@/lib/utils";

/**
 * AlphaStates — demonstrates the score-responsive visual system with the three
 * canonical states (82 strong / 59 moderate / 34 weak). These are explicitly
 * labeled example states of the design system, not live data.
 */
export function AlphaStates() {
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 md:px-6 md:py-28">
        <Reveal>
          <p className="label-caps mb-3">Reading the signal</p>
          <h2 className="max-w-2xl font-display text-3xl font-semibold leading-tight md:text-4xl">
            Color carries the conclusion — not decoration.
          </h2>
          <p className="mt-4 max-w-xl text-muted">
            Analytical scores respond to where they sit in the band system. Raw financial
            numbers stay neutral; only conclusions get semantic color.
          </p>
        </Reveal>

        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {BAND_EXAMPLES.map(({ score, band }, i) => (
            <Reveal key={score} delay={i * 0.08}>
              <div className={cn("border bg-surface p-4", band.border, `${band.bg.replace("/10", "/6")}`)}>
                <ScoreBlock
                  score={score}
                  label="Alpha Score"
                  metric="alpha"
                  size="lg"
                  flat
                />
                <p className="mt-3 border-t border-line pt-3 text-xs leading-relaxed text-muted">
                  {STATE_COPY[i]}
                </p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal className="mt-8">
          <p className="label-caps">Band system</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {BAND_LABELS.map(([range, label, cls]) => (
              <span
                key={label}
                className={cn(
                  "num border px-2.5 py-1 text-xs",
                  cls.text,
                  cls.border,
                  `${cls.bg.replace("/10", "/6")}`,
                )}
              >
                {range} · {label}
              </span>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

const STATE_COPY = [
  "82 — fundamentals, technicals and tone line up. The composite reflects broad agreement across the research dimensions.",
  "59 — strong fundamentals offset by weak price momentum and lukewarm news tone. Moderate by construction, not by rounding.",
  "34 — the analytical dimensions disagree with the trend. The score says the evidence, not the hope.",
];

const BAND_LABELS: Array<
  [string, string, { text: string; bg: string; border: string }]
> = [
  ["80–100", "Strong positive", { text: "text-band-strong", bg: "bg-band-strong/10", border: "border-band-strong/35" }],
  ["60–79", "Positive", { text: "text-band-positive", bg: "bg-band-positive/10", border: "border-band-positive/35" }],
  ["40–59", "Moderate", { text: "text-band-moderate", bg: "bg-band-moderate/10", border: "border-band-moderate/35" }],
  ["20–39", "Weak", { text: "text-band-weak", bg: "bg-band-weak/10", border: "border-band-weak/35" }],
  ["0–19", "Very weak", { text: "text-band-veryweak", bg: "bg-band-veryweak/10", border: "border-band-veryweak/35" }],
];
