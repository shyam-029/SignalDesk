import * as React from "react";

type Theme = "light" | "dark";

const THEME_KEY = "signaldesk-theme";

interface ThemeContextValue {
  theme: Theme;
  toggle: () => void;
}

const ThemeContext = React.createContext<ThemeContextValue>({
  theme: "light",
  toggle: () => {},
});

/** Dark (Warm Ink + Gold) is the primary reference theme; light (Cloud White +
 *  Petrol) is the tuned alternate. First visit starts dark; a stored
 *  preference always wins. */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = React.useState<Theme>(() => {
    if (typeof window === "undefined") return "dark";
    const stored = window.localStorage.getItem(THEME_KEY);
    return stored === "light" ? "light" : "dark";
  });

  React.useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const value = React.useMemo<ThemeContextValue>(
    () => ({
      theme,
      toggle: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    }),
    [theme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return React.useContext(ThemeContext);
}
