import * as React from "react";
import { HelpCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ExplainQuestionType } from "@/lib/types";
import { useExplain } from "@/lib/hooks";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * ExplainAction: a contextual "Why?" affordance wired to the /explain
 * endpoint (Phase 5 LLM architecture with rule-based fallback).
 *
 * Not a chatbot: one fixed question per trigger, one written
 * answer, no chat window, no AI branding. The answer always notes that it is
 * generated from SignalDesk data and is not investment advice.
 */
export function ExplainAction({
  symbol,
  questionType,
  question,
  className,
  triggerLabel,
  variant = "link",
}: {
  symbol: string;
  questionType: ExplainQuestionType;
  question: string;
  triggerLabel?: string;
  className?: string;
  variant?: "link" | "outline";
}) {
  const [open, setOpen] = React.useState(false);
  const explain = useExplain(symbol);

  // Lazy: the first open fires the request; re-openings read the query cache.
  React.useEffect(() => {
    if (open && explain.isIdle) {
      explain.mutate(questionType);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, questionType]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant={variant}
          size="sm"
          className={cn("h-auto px-0 py-0.5 text-xs", variant === "link" && "gap-1", className)}
        >
          <HelpCircle className="size-3.5" />
          {triggerLabel ?? "Why?"}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-84 max-w-[21rem]">
        <p className="label-caps">{question}</p>
        <div className="mt-2.5">
          {explain.isPending && (
            <div className="space-y-2">
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-11/12" />
              <Skeleton className="h-3 w-3/4" />
            </div>
          )}
          {explain.isError && (
            <p className="text-xs leading-relaxed text-band-weak">
              The explanation service could not be reached.
              <button
                className="ml-1 underline underline-offset-2"
                onClick={() => explain.mutate(questionType)}
              >
                Try again
              </button>
            </p>
          )}
          {explain.isSuccess && (
            <p className="text-xs leading-relaxed text-foreground">
              {explain.data.explanation}
            </p>
          )}
        </div>
        <p className="mt-3 border-t border-line pt-2 text-xs leading-relaxed text-faint">
          Generated from SignalDesk data. Not investment advice.
        </p>
      </PopoverContent>
    </Popover>
  );
}
