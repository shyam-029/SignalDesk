export function PageLoader() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-24 md:px-6" aria-busy>
      <div className="space-y-3">
        <div className="h-6 w-48 animate-pulse bg-surface-2" />
        <div className="h-4 w-72 animate-pulse bg-surface-2" />
      </div>
    </div>
  );
}
