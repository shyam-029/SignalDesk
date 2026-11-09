export function SkipLink() {
  return (
    <a
      href="#main-content"
      className="sr-only fixed left-3 top-3 z-[100] bg-foreground px-4 py-2 text-sm text-background focus:not-sr-only"
    >
      Skip to main content
    </a>
  );
}
