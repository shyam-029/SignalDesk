import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import { Reveal } from "@/components/motion/Reveal";
import { Button } from "@/components/ui/button";

/** FinalCTA — the quiet conclusion of the research story. */
export function FinalCTA() {
  return (
    <section>
      <div className="mx-auto max-w-6xl px-4 py-24 text-center md:px-6 md:py-32">
        <Reveal>
          <p className="label-caps mb-4">SignalDesk</p>
          <h2 className="mx-auto max-w-2xl font-display text-3xl font-semibold leading-tight md:text-5xl">
            Better research starts with better questions.
          </h2>
          <p className="mx-auto mt-5 max-w-lg text-muted">
            Why is Alpha 59? Why is the technical score weak? Why is this stock cheaper than
            its peers? Start asking.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Button asChild size="lg" className="gap-2">
              <Link to="/markets">
                Explore SignalDesk
                <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link to="/methodology">View methodology</Link>
            </Button>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
