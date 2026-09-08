import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Search } from "lucide-react";

import { api } from "@/lib/api";
import { StockLogo } from "@/components/stock/StockLogo";
import { cn } from "@/lib/utils";

/**
 * StockSearch: header search over the active ranked universe. Queries the
 * backend's server-side search endpoint (symbol or company name) with a
 * short debounce — the catalog is 2,900+ rows and the old client-side
 * filter over the first page hid every ranked stock beyond row 250
 * (ETERNAL, SWIGGY, IFCI were ranked-in and unfindable). Arrow keys move
 * through the results, Enter opens the highlighted one, Escape dismisses.
 */
export function StockSearch({ className }: { className?: string }) {
  const [query, setQuery] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  const [results, setResults] = React.useState<
    Array<{ symbol: string; name: string }>
  >([]);
  const [loading, setLoading] = React.useState(false);
  const [failed, setFailed] = React.useState(false);
  const navigate = useNavigate();

  const trimmed = query.trim();
  const show = open && trimmed.length > 0;

  // Debounced server-side lookup (250ms): one request per pause in typing.
  React.useEffect(() => {
    if (trimmed.length === 0) {
      setResults([]);
      setLoading(false);
      setFailed(false);
      return;
    }
    setLoading(true);
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api
        .search(trimmed, controller.signal)
        .then((r) => {
          setResults(r.items);
          setFailed(false);
        })
        .catch((e) => {
          if ((e as { name?: string }).name !== "AbortError") setFailed(true);
        })
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [trimmed]);

  const hits = results;
  const activeHit = hits[active] ?? hits[0];

  const select = (symbol: string) => {
    navigate(`/stocks/${encodeURIComponent(symbol.replace(/\.NS$/, ""))}`);
    setQuery("");
    setActive(0);
    setResults([]);
    setOpen(false);
  };

  const onChange = (value: string) => {
    setQuery(value);
    setActive(0);
    setOpen(true);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!show || hits.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % hits.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + hits.length) % hits.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (activeHit) select(activeHit.symbol);
    }
  };

  return (
    <div className={cn("relative min-w-0", className)}>
      <Search
        aria-hidden
        className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint"
      />
      <input
        type="search"
        role="combobox"
        aria-expanded={show}
        aria-controls="stock-search-results"
        aria-autocomplete="list"
        aria-label="Search stocks by ticker or company name"
        placeholder="Search stocks…"
        value={query}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className="h-9 w-full border border-line bg-surface pl-8 pr-2.5 text-sm text-foreground placeholder:text-faint focus:outline-none"
      />

      {show && (
        <div
          id="stock-search-results"
          role="listbox"
          aria-label="Search results"
          // Keep the input focused on item click: mousedown is prevented so
          // the click still lands on the option before any blur handling.
          onMouseDown={(e) => e.preventDefault()}
          className="glass absolute left-0 right-0 top-full z-50 mt-1.5 max-h-80 overflow-y-auto rounded-sm p-1"
        >
          {loading && (
            <p className="flex items-center gap-2 px-3 py-2.5 text-xs text-muted">
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
              Searching…
            </p>
          )}
          {failed && (
            <p className="px-3 py-2.5 text-xs text-band-weak">
              Search failed. Check the API connection and retry.
            </p>
          )}
          {!loading && !failed && hits.length === 0 && (
            <p className="px-3 py-2.5 text-xs text-muted">
              No matches for &ldquo;{trimmed}&rdquo; in the ranked top-1000 universe.
            </p>
          )}
          {hits.map((hit, i) => (
            <button
              key={hit.symbol}
              type="button"
              role="option"
              aria-selected={i === active}
              onClick={() => select(hit.symbol)}
              onMouseEnter={() => setActive(i)}
              className={cn(
                "flex w-full cursor-pointer items-center gap-2.5 px-2 py-1.5 text-left transition-colors",
                i === active ? "bg-surface-2" : "hover:bg-surface-2/60",
              )}
            >
              <StockLogo symbol={hit.symbol} name={hit.name} size="sm" />
              <span className="min-w-0">
                <span className="num block text-xs font-semibold text-foreground">
                  {hit.symbol.replace(/\.NS$/, "")}
                </span>
                <span className="block truncate text-xs text-muted" title={hit.name}>
                  {hit.name}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
