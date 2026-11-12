import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, lazy, Suspense } from "react";
import { MotionConfig } from "framer-motion";

import { ThemeProvider } from "@/components/layout/ThemeProvider";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PageLoader } from "@/components/data/PageLoader";
import { SkipLink } from "@/components/layout/SkipLink";
import LegalPage from "@/pages/LegalPage";
import { persistQueryCache } from "@/lib/queryPersist";
import { loadLandingSnapshot } from "@/lib/landingSnapshot";
import { loadStockSnapshot, symbolFromPath } from "@/lib/stockSnapshot";

const LandingPage = lazy(() => import("@/pages/LandingPage"));
const MarketsPage = lazy(() => import("@/pages/MarketsPage"));
const ScreenerPage = lazy(() => import("@/pages/ScreenerPage"));
const EtfsPage = lazy(() => import("@/pages/EtfsPage"));
const FundsPage = lazy(() => import("@/pages/FundsPage"));
const FundDetailPage = lazy(() => import("@/pages/FundDetailPage"));
const StockDetailPage = lazy(() => import("@/pages/StockDetailPage"));
const MethodologyPage = lazy(() => import("@/pages/MethodologyPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Repeat visits render the last-seen data instantly while fresh data loads.
persistQueryCache(queryClient);

// The landing page's data is also published as a static file after each
// nightly (item 13), so a first visit renders without waiting for the API.
if (typeof window !== "undefined" && window.location.pathname === "/") {
  void loadLandingSnapshot(queryClient);
}

// Same for a direct visit to a stock page: its nightly snapshot is fetched
// from the Cloudflare Worker in parallel with the page's code.
if (typeof window !== "undefined") {
  const stockSymbol = symbolFromPath(window.location.pathname);
  if (stockSymbol) void loadStockSnapshot(queryClient, stockSymbol);
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [pathname]);
  return null;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MotionConfig reducedMotion="user">
          <TooltipProvider delayDuration={250}>
            <BrowserRouter>
              <SkipLink />
              <ScrollToTop />
              <div className="flex min-h-svh flex-col">
                <SiteHeader />
                <main id="main-content" tabIndex={-1} className="flex-1 outline-none">
                  <Suspense fallback={<PageLoader />}>
                    <Routes>
                      <Route path="/" element={<LandingPage />} />
                      <Route path="/markets" element={<MarketsPage />} />
                      <Route path="/screener" element={<ScreenerPage />} />
                      <Route path="/etfs" element={<EtfsPage />} />
                      <Route path="/funds" element={<FundsPage />} />
                      <Route path="/funds/:fundId" element={<FundDetailPage />} />
                      <Route path="/stocks/:symbol" element={<StockDetailPage />} />
                      <Route path="/methodology" element={<MethodologyPage />} />
                      <Route path="/privacy" element={<LegalPage kind="privacy" />} />
                      <Route path="/terms" element={<LegalPage kind="terms" />} />
                      <Route path="/cookies" element={<LegalPage kind="cookies" />} />
                      <Route path="/refunds" element={<LegalPage kind="refund" />} />
                      <Route path="/legal" element={<LegalPage kind="legal" />} />
                      <Route path="*" element={<NotFoundPage />} />
                    </Routes>
                  </Suspense>
                </main>
                <SiteFooter />
              </div>
            </BrowserRouter>
          </TooltipProvider>
        </MotionConfig>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
