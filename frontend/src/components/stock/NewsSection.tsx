import { useNews, useSentiment } from "@/lib/hooks";
import { DataState } from "@/components/data/DataState";
import { CollapsibleSection } from "@/components/stock/CollapsibleSection";
import { InfoDot } from "@/components/data/InfoDot";
import { fmtRelative } from "@/lib/format";
import { sentimentSemantics } from "@/lib/semantic";
import { newsSummary } from "@/lib/summaries";
import { cn } from "@/lib/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, ExternalLink } from "lucide-react";

/**
 * NewsSection: the aggregate sentiment that feeds Alpha's sentiment
 * component, plus the underlying articles. Part of the analytical pipeline,
 * not a news aggregator: articles expand in place for context. Collapsible
 * since Part D: the collapsed header carries the article count and the net
 * sentiment label, only when scored articles exist. Results respect the
 * backend's approximately 30-day freshness window (freshness_days).
 */
export function NewsSection({ symbol }: { symbol: string }) {
  const news = useNews(symbol, 12);
  const sentiment = useSentiment(symbol);

  const sem = sentimentSemantics(sentiment.data?.label);
  const articles = news.data?.items ?? [];
  const summary = newsSummary(articles, sentiment.data?.label);

  return (
    <CollapsibleSection
      id="news"
      index="07"
      kicker="News & sentiment"
      title="What the news is saying"
      summary={summary}
      className="section-alt"
    >

        <div className="grid gap-8 lg:grid-cols-12">
          {/* Aggregate sentiment */}
          <div className="lg:col-span-4">
            <DataState
              loading={sentiment.isLoading}
              error={sentiment.error}
              onRetry={sentiment.refetch}
              insufficient={sentiment.data?.count === 0 || undefined}
              insufficientMessage="No FinBERT-scored articles stored for this symbol yet."
              compact
            >
              {sentiment.data && sentiment.data.count > 0 && (
                <div className={cn("border bg-surface p-5", sem.band.border, `${sem.band.bg.replace("/10", "/6")}`)}>
                  <p className="label-caps flex items-center gap-1.5">
                    Net sentiment
                    <InfoDot metric="net_sentiment" className="size-3.5" />
                  </p>
                  <div className="mt-2 flex items-baseline justify-between">
                    <p className={cn("font-display text-2xl font-semibold", sem.band.text)}>
                      {sem.label}
                    </p>
                    <p className={cn("num text-sm font-medium", sem.band.text)}>
                      {sentiment.data.score > 0 ? "+" : ""}
                      {sentiment.data.score.toFixed(2)}
                    </p>
                  </div>
                  <p className="num mt-1 text-xs text-faint">
                    {sentiment.data.count} FinBERT-scored articles · scale -1 to +1
                  </p>
                  <p className="mt-3 border-t border-line pt-2 text-xs leading-relaxed text-faint">
                    Feeds the sentiment component (30%) of the Alpha Score.
                  </p>
                </div>
              )}
            </DataState>
          </div>

          {/* Articles */}
          <div className="lg:col-span-8">
            <DataState
              loading={news.isLoading}
              error={news.error}
              onRetry={news.refetch}
              empty={Boolean(news.data) && articles.length === 0}
              emptyTitle="No recent news"
              emptyMessage="No articles are stored for this symbol yet."
              compact
            >
              <div className="divide-y divide-line border-y border-line">
                {articles.map((article) => {
                  const label = sentimentSemantics(article.sentiment);
                  return (
                    <Collapsible key={article.id}>
                      <div className="flex items-start justify-between gap-4 py-3">
                        <div className="min-w-0">
                          <CollapsibleTrigger className="group flex w-full items-start justify-between gap-3 text-left">
                            <span className="text-sm leading-snug">{article.title}</span>
                            <ChevronDown className="mt-0.5 size-3.5 shrink-0 text-faint transition-transform group-data-[state=open]:rotate-180" />
                          </CollapsibleTrigger>
                          <p className="num mt-1 text-xs text-faint">
                            {article.source}
                            {article.published_at ? ` · ${fmtRelative(article.published_at)}` : ""}
                          </p>
                        </div>
                        {article.sentiment && (
                          <span
                            className={cn(
                              "shrink-0 border px-1.5 py-0.5 text-xs font-medium",
                              label.band.text,
                              label.band.border,
                            )}
                          >
                            {label.label}
                          </span>
                        )}
                      </div>
                      <CollapsibleContent>
                        <div className="pb-3">
                          <a
                            href={article.url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-cobalt hover:underline dark:text-cobalt-strong"
                          >
                            Read the original article <ExternalLink className="size-3" />
                          </a>
                          <p className="mt-1.5 text-xs leading-relaxed text-faint">
                            Sentiment label produced by FinBERT on the article text; each
                            article contributes to the aggregate net sentiment above.
                          </p>
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  );
                })}
              </div>
            </DataState>
          </div>
        </div>

        {news.data?.freshness_days != null && (
          <p className="num mt-4 text-xs text-faint">
            Showing the last {news.data.freshness_days} days of ingested articles. Sentiment processing is unchanged.
          </p>
        )}
    </CollapsibleSection>
  );
}
