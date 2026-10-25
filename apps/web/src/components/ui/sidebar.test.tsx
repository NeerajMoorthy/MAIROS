import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  Sidebar,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";

/**
 * Below `md` the sidebar overlays the page instead of sitting beside it. That
 * change fixed a 193px horizontal overflow on phones, and introduced two
 * failure modes of its own that these tests pin down: a drawer left covering
 * the page after navigation, and an open drawer painted on first load and then
 * animated shut.
 */

/** Drive `matchMedia` so a test can choose which side of the breakpoint it is on. */
function setViewport(isDesktop: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  const mql = {
    matches: isDesktop,
    media: "(min-width: 768px)",
    addEventListener: (_: string, fn: (event: MediaQueryListEvent) => void) =>
      listeners.add(fn),
    removeEventListener: (_: string, fn: (event: MediaQueryListEvent) => void) =>
      listeners.delete(fn),
    dispatch(matches: boolean) {
      mql.matches = matches;
      listeners.forEach((fn) => fn({ matches } as MediaQueryListEvent));
    },
  };
  window.matchMedia = vi.fn().mockReturnValue(mql) as unknown as typeof window.matchMedia;
  return mql;
}

function Nav({ onNavigate }: { onNavigate?: () => void } = {}) {
  return (
    <SidebarProvider>
      <Sidebar data-testid="aside">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton isActive onClick={onNavigate}>
              Tasks
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </Sidebar>
      <SidebarTrigger />
    </SidebarProvider>
  );
}

const aside = () => screen.getByTestId("aside");
const backdrop = () => screen.queryByRole("button", { name: "Close navigation" });

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("Sidebar on a narrow viewport", () => {
  it("starts closed", async () => {
    setViewport(false);
    render(<Nav />);

    await waitFor(() => expect(aside().className).toContain("w-0"));
    expect(aside().className).not.toContain("w-60");
  });

  it("renders closed below md in the server HTML, so nothing flashes open", async () => {
    // The markup the browser paints *before* hydration is the server's, and
    // that is the frame this guards. Testing Library flushes effects during
    // `render`, so `hydrated` is already true by the time it returns and the
    // pre-hydration frame is unobservable through it — `renderToString` is the
    // frame in question.
    const { renderToString } = await import("react-dom/server");
    const html = renderToString(<Nav />);

    expect(html).toContain("max-md:w-0");
    expect(html).toContain("max-md:invisible");
    // The correction must not be animated either.
    expect(html).toContain("max-md:transition-none");
    // And no backdrop is painted over the page while the browser waits.
    expect(html).not.toContain("Close navigation");
  });

  it("opens as an overlay with a dismissable backdrop", async () => {
    const user = userEvent.setup();
    setViewport(false);
    render(<Nav />);

    await waitFor(() => expect(aside().className).toContain("w-0"));
    await user.click(screen.getByRole("button", { name: "Toggle sidebar" }));

    expect(aside().className).toContain("w-60");
    expect(aside().className).toContain("max-md:fixed");
    expect(backdrop()).toBeInTheDocument();

    await user.click(backdrop()!);
    expect(aside().className).toContain("w-0");
  });

  it("closes itself when a nav item is used", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    setViewport(false);
    render(<Nav onNavigate={onNavigate} />);

    await waitFor(() => expect(aside().className).toContain("w-0"));
    await user.click(screen.getByRole("button", { name: "Toggle sidebar" }));
    expect(aside().className).toContain("w-60");

    await user.click(screen.getByRole("button", { name: /Tasks/ }));

    // The navigation still happens...
    expect(onNavigate).toHaveBeenCalledTimes(1);
    // ...and the drawer no longer covers the page it navigated to. Leaving it
    // open also hid the header's toggle beneath the backdrop, so there was no
    // way back out.
    expect(aside().className).toContain("w-0");
    expect(backdrop()).not.toBeInTheDocument();
  });

  it("keeps its nav buttons out of the tab order while closed", async () => {
    setViewport(false);
    render(<Nav />);

    await waitFor(() => expect(aside().className).toContain("w-0"));
    // `visibility: hidden` is what removes them; a zero-width overflow-hidden
    // container leaves them focusable.
    expect(aside().className).toContain("max-md:invisible");
  });
});

describe("Sidebar on a wide viewport", () => {
  it("starts open and stays open when a nav item is used", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    setViewport(true);
    render(<Nav onNavigate={onNavigate} />);

    await waitFor(() => expect(aside().className).toContain("w-60"));
    expect(backdrop()).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Tasks/ }));

    expect(onNavigate).toHaveBeenCalled();
    expect(aside().className).toContain("w-60");
  });

  it("follows the viewport across the breakpoint", async () => {
    setViewport(true);
    const mql = setViewport(true);
    render(<Nav />);

    await waitFor(() => expect(aside().className).toContain("w-60"));

    mql.dispatch(false);
    await waitFor(() => expect(aside().className).toContain("w-0"));

    mql.dispatch(true);
    await waitFor(() => expect(aside().className).toContain("w-60"));
  });

  it("marks the active item with aria-current, not colour alone", async () => {
    setViewport(true);
    render(<Nav />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Tasks/ })).toHaveAttribute(
        "aria-current",
        "page",
      ),
    );
  });
});
