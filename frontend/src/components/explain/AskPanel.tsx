import * as React from "react";
import { MessageSquareText, X, CornerDownLeft } from "lucide-react";

import type { AskResponse } from "@/lib/types";
import { useAsk } from "@/lib/hooks";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const QUESTION_MAX = 500;

const SUGGESTIONS = [
  "Why is the Alpha score what it is?",
  "How is this stock valued vs peers?",
  "What is driving the fundamentals?",
  "How has it performed over the last year?",
];

const CONFIDENCE_LABEL: Record<AskResponse["confidence"], string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

/**
 * AskPanel: the grounded single-shot research question (Part H). One question
 * at a time about THIS stock's computed data, answered from an allow-listed
 * evidence object by the backend. No chat history, no thread: asking again
 * replaces the previous answer. The backend enforces scope, guards the
 * prompt, and falls back to rule-based answers when the model is unavailable.
 */
export function AskPanel({ symbol, displayName }: { symbol: string; displayName: string }) {
  const [open, setOpen] = React.useState(false);
  const [question, setQuestion] = React.useState("");
  const [result, setResult] = React.useState<AskResponse | null>(null);
  const ask = useAsk(symbol);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const q = question.trim();
    if (!q || ask.isPending) return;
    ask.mutate(q, {
      onSuccess: (data) => setResult(data),
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const close = () => {
    setOpen(false);
    setQuestion("");
    setResult(null);
    ask.reset();
  };

  const blocked =
    ask.error instanceof ApiError && ask.error.detail?.code === "ASK_BLOCKED";
  const trimmed = question.trim();

  return (
    <>
      <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={() => setOpen(true)}>
        <MessageSquareText className="size-3.5" />
        Ask about {displayName}
      </Button>

      {open && (
        <div
          role="dialog"
          aria-label={`Ask a research question about ${displayName}`}
          className="glass fixed bottom-4 right-4 z-50 flex w-[min(26rem,calc(100vw-2rem))] flex-col rounded-sm"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div>
              <p className="label-caps">Ask SignalDesk</p>
              <p className="text-sm font-semibold">{displayName}</p>
            </div>
            <button
              onClick={close}
              aria-label="Close ask panel"
              className="text-faint transition-colors hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>

          <div className="space-y-3 px-4 py-4">
            <textarea
              ref={inputRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value.slice(0, QUESTION_MAX))}
              onKeyDown={onKeyDown}
              rows={3}
              maxLength={QUESTION_MAX}
              placeholder={`Ask about ${symbol} — its scores, valuation, fundamentals, technicals or news…`}
              className="w-full resize-none border border-line bg-surface px-3 py-2 text-sm text-foreground placeholder:text-faint focus:outline-none"
              aria-label="Your question"
            />
            <div className="flex items-center justify-between gap-3">
              <p className="num text-xs text-faint">
                {question.length}/{QUESTION_MAX}
              </p>
              <Button
                size="sm"
                onClick={submit}
                disabled={!trimmed || ask.isPending}
                className="gap-1.5"
              >
                {ask.isPending ? "Asking…" : "Ask"}
                {!ask.isPending && <CornerDownLeft className="size-3.5" aria-hidden />}
              </Button>
            </div>

            {!result && !ask.isPending && !ask.isError && (
              <div>
                <p className="label-caps mb-1.5">Suggested</p>
                <div className="flex flex-wrap gap-1.5">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => {
                        setQuestion(s.slice(0, QUESTION_MAX));
                        inputRef.current?.focus();
                      }}
                      className="cursor-pointer rounded-sm border border-line bg-surface px-2 py-1 text-left text-xs text-muted transition-colors hover:border-cobalt hover:text-cobalt dark:hover:text-cobalt-strong"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {ask.isPending && (
              <div className="space-y-2 border-l-2 border-cobalt/40 pl-3" aria-live="polite">
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-10/12" />
                <Skeleton className="h-3 w-3/4" />
              </div>
            )}

            {ask.isError && (
              <div className="border-l-2 border-band-weak/60 pl-3" aria-live="polite">
                {blocked ? (
                  <p className="text-xs leading-relaxed text-band-weak">
                    This question was blocked by safety filters. Rephrase it as a
                    question about the stock&apos;s research data.
                  </p>
                ) : (
                  <p className="text-xs leading-relaxed text-band-weak">
                    The ask service could not be reached.
                    <button
                      type="button"
                      className="ml-1 cursor-pointer underline underline-offset-2"
                      onClick={() => trimmed && ask.mutate(trimmed, { onSuccess: (d) => setResult(d) })}
                    >
                      Try again
                    </button>
                  </p>
                )}
              </div>
            )}

            {result && (
              <div className="border-l-2 border-cobalt/40 pl-3" aria-live="polite">
                <p className="text-xs leading-relaxed text-foreground">{result.answer}</p>
                {result.evidence.length > 0 && (
                  <div className="mt-2.5">
                    <p className="label-caps mb-1">Evidence used</p>
                    <ul className="space-y-0.5">
                      {result.evidence.map((e, i) => (
                        <li key={i} className="num text-xs leading-relaxed text-muted">
                          · {e}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <p
                  className={cn(
                    "mt-2.5 inline-block border px-1.5 py-0.5 text-xs font-medium",
                    result.confidence === "high" && "border-band-positive/40 text-band-positive",
                    result.confidence === "medium" && "border-band-moderate/40 text-band-moderate",
                    result.confidence === "low" && "border-band-weak/40 text-band-weak",
                  )}
                >
                  {CONFIDENCE_LABEL[result.confidence]}
                </p>
              </div>
            )}
          </div>

          <p className="border-t border-line px-4 py-3 text-xs leading-relaxed text-faint">
            One question at a time, answered from {symbol}&apos;s computed SignalDesk
            data only. Not investment advice.
          </p>
        </div>
      )}
    </>
  );
}
