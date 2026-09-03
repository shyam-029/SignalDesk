import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Self-hosted type system: Libre Caslon (display), Hanken Grotesk (body),
// JetBrains Mono (financial data).
import "@fontsource/libre-caslon-text/400.css";
import "@fontsource/libre-caslon-text/700.css";
import "@fontsource/hanken-grotesk/400.css";
import "@fontsource/hanken-grotesk/500.css";
import "@fontsource/hanken-grotesk/600.css";
import "@fontsource/hanken-grotesk/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";

import "./index.css";
import App from "@/App";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element missing");

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
