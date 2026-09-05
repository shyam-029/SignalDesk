import { Link } from "react-router-dom";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto max-w-6xl px-4 py-10 md:px-6">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-baseline">
          <div>
            <p className="font-display text-base font-bold">SignalDesk</p>
            <p className="mt-1 max-w-md text-xs leading-relaxed text-muted">
              Fundamentals, relative valuation, technicals and sentiment, combined into one
              research signal for Indian equities. Analysis is informational only and
              not investment advice.
            </p>
          </div>
          <nav className="flex gap-5 text-xs text-muted">
            <Link to="/markets" className="hover:text-foreground">
              Markets
            </Link>
            <Link to="/screener" className="hover:text-foreground">
              Screener
            </Link>
            <Link to="/methodology" className="hover:text-foreground">
              Methodology
            </Link>
          </nav>
        </div>
        <p className="label-caps mt-8">
          Nifty 250 universe Â· prices via Yahoo Finance Â· sentiment via FinBERT
        </p>
      </div>
    </footer>
  );
}

