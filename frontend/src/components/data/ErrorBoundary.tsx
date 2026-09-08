import * as React from "react";

import { Button } from "@/components/ui/button";

interface Props {
  children: React.ReactNode;
  /** Short label identifying the section in the fallback ("Alpha", ...). */
  label: string;
  onRetry?: () => void;
}

interface State {
  error: Error | null;
}

/**
 * ErrorBoundary: one crashed section must never blank the whole research
 * page (IFCI loaded and then went blank when a single section threw during
 * render). Each stock-page section renders inside its own boundary: the
 * failure is contained to a compact retry card and the rest of the page
 * stays up.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error): void {
    // Console only: no telemetry backend exists; the envelope convention is
    // a backend concept. Keep the trace visible during development.
    console.error(`[${this.props.label}] section crashed:`, error);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          className="flex items-start gap-3 border border-dashed border-line bg-surface px-4 py-4"
          role="alert"
        >
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">
              The {this.props.label} section could not render
            </p>
            <p className="mt-0.5 text-xs text-muted">
              Something in this section failed. The rest of the page is unaffected.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => this.setState({ error: null })}
            className="shrink-0"
          >
            Retry
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
