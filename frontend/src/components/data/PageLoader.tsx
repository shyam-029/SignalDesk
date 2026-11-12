import { SignalWave } from "@/components/layout/SignalWave";

/** Route-level loading state: the signal wave drawing itself. */
export function PageLoader() {
  return (
    <div
      className="mx-auto flex max-w-6xl flex-col items-center gap-3 px-4 py-32 md:px-6"
      role="status"
      aria-busy
    >
      <SignalWave drawing className="h-8 w-20 text-cobalt dark:text-cobalt-strong" />
      <p className="label-caps">Loading</p>
    </div>
  );
}
