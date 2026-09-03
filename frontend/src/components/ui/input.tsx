import * as React from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-24 bg-surface px-2 text-sm num text-foreground placeholder:text-faint",
        "border border-line transition-colors hover:border-rule focus:border-cobalt focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 bg-surface px-2 text-sm text-foreground",
        "border border-line transition-colors hover:border-rule focus:border-cobalt focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}
