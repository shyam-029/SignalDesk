import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Normalize a user/URL symbol to the canonical exchange form: "reliance" → "RELIANCE". */
export function normalizeSymbol(symbol: string): string {
  const s = symbol.trim().toUpperCase();
  return s.endsWith(".NS") ? s.slice(0, -3) : s;
}
