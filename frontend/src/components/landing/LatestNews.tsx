import { Link } from "react-router-dom";

import { useMarketNews } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { cn } from "@/lib/utils";

/**
 * LatestNews: the newest stored headlines across the universe, each tagged
 * with the company it was filed under and the tone FinBERT scored it at.
 * Headlines open at their source; the ticker opens the company's page. An
 * article without a score shows no tone at all (never a default "neutral").
 */

const TONE: Record<string, string> = {
  positive: "text-up",
  negative: "text-down",
  neutral: "text-faint",
};

export function LatestNews() {
  const query = useMarketNews(8);
  const items = query.data?.items ?? [];

  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-16 md:px-6 md:py-20">
        <div className="grid gap-10 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <p className="label-caps mb-1.5">News, read by a model</p>
            <h2 className="font-display text-2xl font-semibold leading-tight tracking-[-0.01em] md:text-[26px]">
              Every headline gets a tone, and the tone feeds the score
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              Headlines are matched to a company, scored positive, negative or neutral by
              FinBERT, and averaged into the sentiment part of the Alpha Score. These are
              the latest ones stored.
            </p>
          </div>

          <div className="lg:col-span-8">
            <DataState
              loading={query.isLoading}
              error={query.error}
              onRetry={query.refetch}
              empty={Boolean(query.data) && items.length === 0}
              emptyTitle="No articles yet"
              emptyMessage="News ingestion has not stored any headlines yet."
              compact
            >
              <ul className="border-y border-line">
                {items.map((a) => {
                  const bare = a.symbol.replace(".NS", "");
                  return (
                    <li key={a.id} className="flex gap-4 border-b border-line py-3.5 last:border-b-0">
                      <Link
                        to={`/stocks/${encodeURIComponent(bare)}`}
                        className="num w-24 shrink-0 truncate pt-0.5 text-xs font-semibold text-muted hover:text-cobalt dark:hover:text-cobalt-strong"
                      >
                        {bare}
                      </Link>
                      <div className="min-w-0 flex-1">
                        <a
                          href={a.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-sm leading-snug underline-offset-4 hover:underline"
                        >
                          {a.title}
                        </a>
                        <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-faint">
                          <span>{a.source}</span>
                          {a.published_at && (
                            <span>{new Date(a.published_at).toLocaleDateString("en-IN")}</span>
                          )}
                        </p>
                      </div>
                      {a.sentiment && (
                        <span
                          className={cn(
                            "w-16 shrink-0 pt-0.5 text-right text-xs font-medium capitalize",
                            TONE[a.sentiment] ?? "text-faint",
                          )}
                        >
                          {a.sentiment}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </DataState>
          </div>
        </div>
      </div>
    </section>
  );
}
