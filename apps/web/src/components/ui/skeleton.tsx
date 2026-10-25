import { cn } from "@/lib/utils";

/**
 * Loading placeholder.
 *
 * Carries `role="status"` so the wait is announced to a screen reader rather
 * than being a silent visual-only cue — and so tests can assert on "is this
 * loading?" without reaching for a CSS class.
 */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={cn("animate-pulse-dot rounded-md bg-muted", className)}
      {...props}
    />
  );
}

export { Skeleton };
