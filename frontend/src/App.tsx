import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { lazy, Suspense } from "react";

import { ThemeProvider } from "@/components/layout/ThemeProvider";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PageLoader } from "@/components/data/PageLoader";

// Pages are lazy-loaded so each route ships as its own chunk — the landing
// page never pays for the stock research experience up front.
const LandingPage = lazy(() => import("@/pages/LandingPage"));
const MarketsPage = lazy(() => import("@/pages/MarketsPage"));
const ScreenerPage = lazy(() => import("@/pages/ScreenerPage"));
const StockDetailPage = lazy(() => import("@/pages/StockDetailPage"));
const MethodologyPage = lazy(() => import("@/pages/MethodologyPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Data is daily; a missed request should not blank the UI. Retries are
      // configured per-hook (404s never retry).
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

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
        <TooltipProvider delayDuration={250}>
          <BrowserRouter>
            <ScrollToTop />
            <div className="flex min-h-svh flex-col">
              <SiteHeader />
              <main className="flex-1">
                <Suspense fallback={<PageLoader />}>
                  <Routes>
                    <Route path="/" element={<LandingPage />} />
                    <Route path="/markets" element={<MarketsPage />} />
                    <Route path="/screener" element={<ScreenerPage />} />
                    <Route path="/stocks/:symbol" element={<StockDetailPage />} />
                    <Route path="/methodology" element={<MethodologyPage />} />
                    <Route path="*" element={<NotFoundPage />} />
                  </Routes>
                </Suspense>
              </main>
              <SiteFooter />
            </div>
          </BrowserRouter>
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
