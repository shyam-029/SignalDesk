import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Self-hosted type system: Libre Caslon (display), Instrument Sans (body),
// IBM Plex Mono (financial data, weight 500+).
import "@fontsource/libre-caslon-text/400.css";
import "@fontsource/libre-caslon-text/700.css";
import "@fontsource/instrument-sans/400.css";
import "@fontsource/instrument-sans/500.css";
import "@fontsource/instrument-sans/600.css";
import "@fontsource/instrument-sans/700.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-mono/700.css";

import "./index.css";
import App from "@/App";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element missing");

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
