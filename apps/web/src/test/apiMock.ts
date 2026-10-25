import { vi } from "vitest";

/**
 * A stand-in for the typed API client where every method is a fresh `vi.fn()`.
 *
 * Returned as a Proxy so a test only has to configure the calls it cares
 * about: any method a component reaches for exists and resolves through
 * `vi.mocked(...)`, and one that is never configured simply returns
 * `undefined` rather than exploding somewhere unrelated.
 */
export function makeApiProxy(): Record<string, ReturnType<typeof vi.fn>> {
  const created: Record<string, ReturnType<typeof vi.fn>> = {};
  return new Proxy(created, {
    get(target, property: string) {
      if (!(property in target)) {
        target[property] = vi.fn();
      }
      return target[property];
    },
  });
}
