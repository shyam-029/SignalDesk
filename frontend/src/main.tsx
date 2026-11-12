import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Self-hosted type system: Newsreader (headlines), IBM Plex Sans (text,
// interface and every number, with tabular figures), IBM Plex Mono (ticker
// symbols only).
import "@fontsource/newsreader/500.css";
import "@fontsource/newsreader/600.css";
import "@fontsource/newsreader/700.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";

import "./index.css";
import App from "@/App";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element missing");

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
