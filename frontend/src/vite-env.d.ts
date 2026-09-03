/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Override the SignalDesk API base (defaults to /api/v1, proxied in dev). */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
