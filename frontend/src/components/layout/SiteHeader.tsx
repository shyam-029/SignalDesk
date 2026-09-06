import { Link, NavLink } from "react-router-dom";
import { Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";
import { useTheme } from "@/components/layout/ThemeProvider";
import { StockSearch } from "@/components/layout/StockSearch";
import { Button } from "@/components/ui/button";

const NAV = [
  { to: "/markets", label: "Markets" },
  { to: "/screener", label: "Screener" },
  { to: "/methodology", label: "Methodology" },
];

export function SiteHeader() {
  const { theme, toggle } = useTheme();
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 md:gap-6 md:px-6">
        <Link to="/" className="flex shrink-0 items-baseline gap-2">
          <span className="font-display text-lg font-bold tracking-[-0.01em]">SignalDesk</span>
          <span className="label-caps hidden sm:inline">Research</span>
        </Link>

        <StockSearch className="w-full max-w-xs md:max-w-sm" />

        <nav className="ml-auto flex shrink-0 items-center gap-1 md:gap-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "px-2.5 py-1.5 text-sm font-medium text-muted transition-colors hover:text-foreground",
                  isActive && "text-foreground",
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
          <Button
            variant="ghost"
            size="icon"
            onClick={toggle}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
        </nav>
      </div>
    </header>
  );
}
