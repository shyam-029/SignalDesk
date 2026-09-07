import * as React from "react";
import { MessageSquareText, X, CornerDownLeft } from "lucide-react";
import { Link } from "react-router-dom";

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
 * at a time about this stock's computed data. The explicit acknowledgement
 * tells users where the submitted question is processed before they send it.
 */
export function AskPanel({ symbol, displayName }: { symbol: string; displayName: string }) {
  const [open, setOpen] = React.useState(false);
  const [question, setQuestion] = React.useState("");
  const [acknowledged, setAcknowledged] = React.useState(false);
  const [result, setResult] = React.useState<AskResponse | null>(null);
  const ask = useAsk(symbol);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);

  React.useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const submit = () => {
    const q = question.trim();
    if (!q || ask.isPending || !acknowledged) return;
    ask.mutate(q, { onSuccess: (data) => setResult(data) });
  };

  const close = () => {
    setOpen(false);
    setQuestion("");
    setAcknowledged(false);
    setResult(null);
    ask.reset();
  };

  const blocked = ask.error instanceof ApiError && ask.error.code === "ASK_BLOCKED";
  const trimmed = question.trim();

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-1.5 text-xs"
        onClick={() => setOpen(true)}
      >
        <MessageSquareText className="size-3.5" aria-hidden />
        Ask about {displayName}
      </Button>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Ask a research question about ${displayName}`}
          className="glass fixed bottom-4 right-4 z-50 flex w-[min(26rem,calc(100vw-2rem))] flex-col rounded-sm"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div>
              <p className="label-caps">Ask SignalDesk</p>
              <p className="text-sm font-semibold">{displayName}</p>
            </div>
            <button
              type="button"
              onClick={close}
              aria-label="Close research question panel"
              className="p-1 text-faint transition-colors hover:text-foreground"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>

          <form
            className="space-y-3 px-4 py-4"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <label htmlFor="ask-question" className="label-caps block">Your research question</label>
            <textarea
              id="ask-question"
              ref={inputRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value.slice(0, QUESTION_MAX))}
              rows={3}
              maxLength={QUESTION_MAX}
              placeholder={`Ask about ${symbol} — its scores, valuation, fundamentals, technicals or news…`}
              className="w-full resize-none border border-line bg-surface px-3 py-2 text-sm text-foreground placeholder:text-faint focus:outline-none"
              aria-describedby="ask-processing-note ask-character-count"
            />
            <div className="flex items-center justify-between gap-3">
              <p id="ask-character-count" className="num text-xs text-faint">
                {question.length}/{QUESTION_MAX}
              </p>
              <Button
                type="submit"
                size="sm"
                disabled={!trimmed || !acknowledged || ask.isPending}
                className="gap-1.5"
              >
                {ask.isPending ? "Asking…" : "Submit question"}
                {!ask.isPending && <CornerDownLeft className="size-3.5" aria-hidden />}
              </Button>
            </div>

            <label className="flex cursor-pointer items-start gap-2 text-xs leading-relaxed text-muted">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                className="mt-1 size-3.5 shrink-0 accent-[var(--cobalt)]"
              />
              <span id="ask-processing-note">
                I understand that this question and the research context needed to answer it are processed by the
                configured LLM provider. I will not submit sensitive personal information. See the{" "}
                <Link className="text-cobalt underline underline-offset-2" to="/privacy" target="_blank" rel="noreferrer">
                  Privacy Policy
                </Link>.
              </span>
            </label>

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
                {(() => {
                  if (blocked) {
                    return <p className="text-xs leading-relaxed text-band-weak">This question was blocked by safety filters. Rephrase it as a question about the stock&apos;s research data.</p>;
                  }
                  const err = ask.error as ApiError | undefined;
                  if (err?.code === "HTTP_404") {
                    return <p className="text-xs leading-relaxed text-band-weak">The ask endpoint is not on the running backend. Restart the backend server to pick it up.</p>;
                  }
                  if (err && (err.status >= 500 || err.code === "NETWORK_ERROR")) {
                    return (
                      <p className="text-xs leading-relaxed text-band-weak">
                        The ask service could not be reached.
                        <button type="button" className="ml-1 cursor-pointer underline underline-offset-2" onClick={() => trimmed && ask.mutate(trimmed, { onSuccess: (d) => setResult(d) })}>Try again</button>
                      </p>
                    );
                  }
                  return <p className="text-xs leading-relaxed text-band-weak">{err?.message ?? "The question could not be answered."}</p>;
                })()}
              </div>
            )}

            {result && (
              <div className="border-l-2 border-cobalt/40 pl-3" aria-live="polite">
                <p className="text-xs leading-relaxed text-foreground">{result.answer}</p>
                {result.evidence.length > 0 && (
                  <div className="mt-2.5">
                    <p className="label-caps mb-1">Evidence used</p>
                    <ul className="space-y-0.5">
                      {result.evidence.map((e, i) => <li key={i} className="num text-xs leading-relaxed text-muted">· {e}</li>)}
                    </ul>
                  </div>
                )}
                <p className={cn("mt-2.5 inline-block border px-1.5 py-0.5 text-xs font-medium", result.confidence === "high" && "border-band-positive/40 text-band-positive", result.confidence === "medium" && "border-band-moderate/40 text-band-moderate", result.confidence === "low" && "border-band-weak/40 text-band-weak")}>{CONFIDENCE_LABEL[result.confidence]}</p>
              </div>
            )}
          </form>

          <p className="border-t border-line px-4 py-3 text-xs leading-relaxed text-faint">
            One question at a time, answered from {symbol}&apos;s computed SignalDesk data only. Not investment advice.
          </p>
        </div>
      )}
    </>
  );
}
