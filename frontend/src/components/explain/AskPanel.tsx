import * as React from "react";
import { MessageSquareText } from "lucide-react";

import type { ExplainQuestionType } from "@/lib/types";
import { useExplain } from "@/lib/hooks";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * AskPanel: "Ask about {SYMBOL}", a small popover listing the five research
 * question types. Selecting one runs the /explain mutation inline. No chat
 * window, no free-text input; the questions are fixed.
 */
export function AskPanel({ symbol, displayName }: { symbol: string; displayName: string }) {
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState<ExplainQuestionType | null>(null);
  const explain = useExplain(symbol);

  const questions: Array<{ type: ExplainQuestionType; label: string }> = [
    { type: "alpha", label: "Why is the Alpha score what it is?" },
    { type: "technical", label: "Why is the technical score what it is?" },
    { type: "valuation", label: "Why is this valued where it is vs peers?" },
    { type: "fundamental", label: "What is driving the fundamental scores?" },
    { type: "sentiment", label: "What is the news sentiment saying?" },
  ];

  const run = (type: ExplainQuestionType) => {
    setActive(type);
    explain.mutate(type);
  };

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setActive(null);
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5 text-xs">
          <MessageSquareText className="size-3.5" />
          Ask about {displayName}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 max-w-[24rem]">
        {!active && (
          <>
            <p className="label-caps">Research questions</p>
            <div className="mt-2 grid gap-0.5">
              {questions.map((q) => (
                <button
                  key={q.type}
                  onClick={() => run(q.type)}
                  className="rounded-sm px-2 py-1.5 text-left text-xs text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
                >
                  {q.label}
                </button>
              ))}
            </div>
          </>
        )}
        {active && (
          <>
            <button
              onClick={() => setActive(null)}
              className="text-xs text-cobalt hover:underline dark:text-cobalt-strong"
            >
              ← All questions
            </button>
            <p className="mt-2.5 text-xs font-semibold">
              {questions.find((q) => q.type === active)?.label}
            </p>
            <div className="mt-2">
              {explain.isPending && (
                <div className="space-y-2">
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-3 w-10/12" />
                </div>
              )}
              {explain.isError && (
                <p className="text-xs text-band-weak">
                  Could not reach the explanation service.
                  <button className="ml-1 underline" onClick={() => run(active)}>
                    Retry
                  </button>
                </p>
              )}
              {explain.isSuccess && (
                <p className="text-xs leading-relaxed text-foreground">
                  {explain.data.explanation}
                </p>
              )}
            </div>
          </>
        )}
        <p className={cn("mt-3 border-t border-line pt-2 text-xs leading-relaxed text-faint")}>
          Generated from SignalDesk data. Not investment advice.
        </p>
      </PopoverContent>
    </Popover>
  );
}
