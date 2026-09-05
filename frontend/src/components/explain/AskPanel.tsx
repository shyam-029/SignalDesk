import * as React from "react";
import { MessageSquareText, X } from "lucide-react";

import type { ExplainQuestionType } from "@/lib/types";
import { useExplain } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface ThreadEntry {
  id: number;
  question: string;
  type: ExplainQuestionType;
  answer?: string;
}

/**
 * AskPanel: "Ask about {name}" opens a chat-style research window: the five
 * fixed, grounded question types as chips, with every asked question and its
 * SignalDesk-generated answer kept in a scrollable thread so follow-ups read
 * like a conversation. Free-form chat arrives with the LLM work; the
 * grounded question set is what the backend can answer without inventing.
 */
export function AskPanel({ symbol, displayName }: { symbol: string; displayName: string }) {
  const [open, setOpen] = React.useState(false);
  const [thread, setThread] = React.useState<ThreadEntry[]>([]);
  const explain = useExplain(symbol);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  const questions: Array<{ type: ExplainQuestionType; label: string; short: string }> = [
    { type: "alpha", label: "Why is the Alpha score what it is?", short: "Alpha score" },
    { type: "technical", label: "Why is the technical score what it is?", short: "Technicals" },
    { type: "valuation", label: "Why is this valued where it is vs peers?", short: "Valuation" },
    { type: "fundamental", label: "What is driving the fundamental scores?", short: "Fundamentals" },
    { type: "sentiment", label: "What is the news sentiment saying?", short: "Sentiment" },
  ];

  const ask = (type: ExplainQuestionType) => {
    const entry = {
      id: Date.now() + Math.random(),
      question: questions.find((q) => q.type === type)?.short ?? type,
      type,
    };
    setThread((t) => [...t, entry]);
    explain.reset();
    explain.mutate(type);
  };

  // Keep the newest answer in view as the thread grows.
  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [thread.length, explain.isPending, explain.isSuccess]);

  // Persist each resolved answer onto its own thread entry, so earlier
  // questions keep their answers when a new one is asked.
  React.useEffect(() => {
    if (explain.isSuccess && explain.data) {
      setThread((t) => {
        if (t.length === 0 || t[t.length - 1].answer) return t;
        const next = [...t];
        next[next.length - 1] = {
          ...next[next.length - 1],
          answer: explain.data!.explanation,
        };
        return next;
      });
    }
  }, [explain.isSuccess, explain.data]);

  return (
    <>
      <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={() => setOpen(true)}>
        <MessageSquareText className="size-3.5" />
        Ask about {displayName}
      </Button>

      {open && (
        <div
          role="dialog"
          aria-label={`Research questions about ${displayName}`}
          className="glass fixed bottom-4 right-4 z-50 flex w-[min(26rem,calc(100vw-2rem))] flex-col rounded-sm"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div>
              <p className="label-caps">Research chat</p>
              <p className="text-sm font-semibold">{displayName}</p>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close research chat"
              className="text-faint transition-colors hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>

          <div ref={scrollRef} className="max-h-80 min-h-40 space-y-4 overflow-y-auto px-4 py-4">
            {thread.length === 0 && (
              <p className="text-xs leading-relaxed text-muted">
                Pick a question below. Every answer is generated from this stock&apos;s
                computed research data, never invented.
              </p>
            )}
            {thread.map((entry, i) => {
              const isLast = i === thread.length - 1;
              const showState = isLast && entry.answer == null;
              return (
                <div key={entry.id}>
                  <p className="ml-auto w-fit rounded-sm bg-surface-2 px-2.5 py-1.5 text-xs font-medium">
                    {entry.question}
                  </p>
                  <div className="mt-2 border-l-2 border-cobalt/40 pl-3">
                    {showState && explain.isPending && (
                      <div className="space-y-2 py-1">
                        <Skeleton className="h-3 w-full" />
                        <Skeleton className="h-3 w-10/12" />
                      </div>
                    )}
                    {showState && explain.isError && (
                      <p className="text-xs text-band-weak">
                        Could not reach the explanation service.
                        <button
                          className="ml-1 underline"
                          onClick={() => explain.mutate(entry.type)}
                        >
                          Retry
                        </button>
                      </p>
                    )}
                    {entry.answer != null && (
                      <p className="text-xs leading-relaxed text-foreground">{entry.answer}</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="border-t border-line px-4 py-3">
            <div className="flex flex-wrap gap-1.5">
              {questions.map((q) => (
                <button
                  key={q.type}
                  onClick={() => ask(q.type)}
                  disabled={explain.isPending}
                  className={cn(
                    "rounded-sm border border-line bg-surface px-2 py-1 text-xs text-muted",
                    "transition-colors hover:border-cobalt hover:text-cobalt dark:hover:text-cobalt-strong",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                  )}
                >
                  {q.short}
                </button>
              ))}
            </div>
            <p className="mt-2.5 text-xs leading-relaxed text-faint">
              Free-form questions arrive with the LLM release. Generated from SignalDesk
              data. Not investment advice.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
