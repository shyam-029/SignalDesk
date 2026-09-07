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

const LandingPage = lazy(() => import("@/pages/LandingPage"));
const MarketsPage = lazy(() => import("@/pages/MarketsPage"));
const ScreenerPage = lazy(() => import("@/pages/ScreenerPage"));
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
