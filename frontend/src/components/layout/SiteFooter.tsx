import { Link } from "react-router-dom";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto max-w-6xl px-4 py-10 md:px-6">
        <div className="flex flex-col justify-between gap-8 md:flex-row md:items-baseline">
          <div>
            <p className="font-display text-base font-bold">SignalDesk</p>
            <p className="mt-1 max-w-md text-xs leading-relaxed text-muted">
              Fundamentals, relative valuation, technicals and sentiment, combined into one
              research signal for Indian equities. Analysis is informational only and
              not investment advice.
            </p>
          </div>
          <nav aria-label="Footer navigation" className="grid grid-cols-2 gap-x-8 gap-y-2 text-xs text-muted sm:grid-cols-3">
            <Link to="/markets" className="hover:text-foreground">Markets</Link>
            <Link to="/screener" className="hover:text-foreground">Screener</Link>
            <Link to="/methodology" className="hover:text-foreground">Methodology</Link>
            <Link to="/privacy" className="hover:text-foreground">Privacy</Link>
            <Link to="/terms" className="hover:text-foreground">Terms</Link>
            <Link to="/cookies" className="hover:text-foreground">Cookies</Link>
            <Link to="/refunds" className="hover:text-foreground">Refunds</Link>
            <Link to="/legal" className="hover:text-foreground">Business details</Link>
          </nav>
        </div>
        <p className="label-caps mt-8">
          Nifty 250 universe · prices via provider integrations · sentiment via FinBERT
        </p>
        <p className="mt-3 max-w-4xl text-xs leading-relaxed text-faint">
          Market data and news are sourced through third-party provider integrations. SignalDesk does not guarantee
          completeness, accuracy, timeliness, or availability of third-party data. Nothing on this site is investment advice.
        </p>
      </div>
    </footer>
  );
}
