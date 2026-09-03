import * as React from "react";
import { AlertTriangle, DatabaseZap, RefreshCw, SearchX } from "lucide-react";

import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

/**
 * DataState — the single component through which every data-driven region
 * renders its non-ready states: loading, error, empty, insufficient, stale.
 * Missing backend data is NEVER filled with fake values; each state says what
 * actually happened and offers a retry where retrying is meaningful.
 */
export interface DataStateProps {
  loading?: boolean;
  error?: ApiError | Error | null;
  onRetry?: () => void;
  empty?: boolean;
  insufficient?: boolean;
  /** As-of label (e.g. "12 Aug 2026"); renders a stale-data chip when set. */
  asOf?: string | null;
  skeleton?: React.ReactNode;
  emptyTitle?: string;
  emptyMessage?: string;
  insufficientTitle?: string;
  insufficientMessage?: string;
  compact?: boolean;
  className?: string;
  children?: React.ReactNode;
}

export function DataState({
  loading,
  error,
  onRetry,
  empty,
  insufficient,
  asOf,
  skeleton,
  emptyTitle = "No data yet",
  emptyMessage = "Nothing to show here yet.",
  insufficientTitle = "Insufficient data",
  insufficientMessage = "SignalDesk does not have enough stored data to compute this yet. Nothing is estimated in the meantime.",
  compact,
  className,
  children,
}: DataStateProps) {
  const state = resolveState({ loading, error, empty, insufficient });

  return (
    <div className={className}>
      {state === "loading" &&
        (skeleton ?? <DefaultSkeleton compact={compact} />)}
      {state === "error" && <ErrorState error={error!} onRetry={onRetry} compact={compact} />}
      {state === "insufficient" && (
        <NoteState
          icon={<DatabaseZap className="size-4 text-faint" />}
          title={insufficientTitle}
          message={insufficientMessage}
          compact={compact}
        />
      )}
      {state === "empty" && (
        <NoteState
          icon={<SearchX className="size-4 text-faint" />}
          title={emptyTitle}
          message={emptyMessage}
          compact={compact}
        />
      )}
      {state === "ready" && (
        <>
          {asOf && <StaleChip asOf={asOf} />}
          {children}
        </>
      )}
    </div>
  );
}

type State = "loading" | "error" | "insufficient" | "empty" | "ready";

function resolveState(p: DataStateProps): State {
  if (p.loading) return "loading";
  if (p.error) return "error";
  if (p.insufficient) return "insufficient";
  if (p.empty) return "empty";
  return "ready";
}

function DefaultSkeleton({ compact }: { compact?: boolean }) {
  return (
    <div className={compact ? "space-y-2" : "space-y-3"}>
      <div className="h-4 w-40 animate-pulse bg-surface-2" />
      <div className="h-4 w-64 animate-pulse bg-surface-2" />
      {!compact && <div className="h-4 w-52 animate-pulse bg-surface-2" />}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  compact,
}: {
  error: ApiError | Error;
  onRetry?: () => void;
  compact?: boolean;
}) {
  const isApi = error instanceof ApiError;
  const unknownStock = isApi && error.isNotFound;
  const title = unknownStock
    ? "Unknown symbol"
    : isApi && error.status === 0
      ? "API unreachable"
      : "Something went wrong";
  const message = unknownStock
    ? "No company with this symbol exists in the SignalDesk catalog."
    : isApi
      ? error.message
      : "An unexpected error occurred.";

  return (
    <div
      className={cn(
        "flex items-start gap-3 border border-line bg-surface px-4",
        compact ? "py-3" : "py-5",
      )}
      role="alert"
    >
      {unknownStock ? (
        <SearchX className="mt-0.5 size-4 shrink-0 text-faint" />
      ) : (
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-band-weak" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">{title}</p>
        <p className="mt-0.5 text-xs text-muted">{message}</p>
        {isApi && error.code === "NETWORK_ERROR" && (
          <p className="mt-0.5 text-xs text-faint">
            Check that the FastAPI backend is running (default http://localhost:8000).
          </p>
        )}
      </div>
      {onRetry && !unknownStock && (
        <Button variant="outline" size="sm" onClick={onRetry} className="shrink-0">
          <RefreshCw className="size-3.5" />
          Retry
        </Button>
      )}
    </div>
  );
}

function NoteState({
  icon,
  title,
  message,
  compact,
}: {
  icon: React.ReactNode;
  title: string;
  message: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-3 border border-dashed border-line bg-transparent px-4",
        compact ? "py-3" : "py-5",
      )}
    >
      {icon}
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <p className="mt-0.5 text-xs text-muted">{message}</p>
      </div>
    </div>
  );
}

function StaleChip({ asOf }: { asOf: string }) {
  return (
    <p className="label-caps mb-3">
      As of <span className="num normal-case tracking-normal text-muted">{asOf}</span>
    </p>
  );
}
