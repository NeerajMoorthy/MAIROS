"use client";

import * as React from "react";
import { PanelLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Collapsible application sidebar.
 *
 * A trimmed version of the shadcn/ui sidebar: same component names and
 * composition model, without the mobile sheet and cookie persistence that the
 * mid-review build does not need.
 */

type SidebarContextValue = {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  /** False during SSR and the first client render — see SidebarProvider. */
  hydrated: boolean;
  /** True above the `md` breakpoint, where the sidebar sits in the flow. */
  isDesktop: boolean;
  /** Close the sidebar, but only where it overlays the content. */
  closeIfOverlaying: () => void;
};

const SidebarContext = React.createContext<SidebarContextValue | null>(null);

export function useSidebar() {
  const context = React.useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used within a <SidebarProvider>");
  }
  return context;
}

/** Below this width the sidebar starts closed and overlays rather than pushes. */
const DESKTOP_QUERY = "(min-width: 768px)";

export function SidebarProvider({
  defaultOpen = true,
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { defaultOpen?: boolean }) {
  const [open, setOpen] = React.useState(defaultOpen);
  const [hydrated, setHydrated] = React.useState(false);
  const [isDesktop, setIsDesktop] = React.useState(true);

  /*
   * The sidebar used to open by default at every width. On a 375px phone its
   * 240px left the rest of the app 135px, which pushed the header — and with
   * it the page — 193px past the viewport. It now starts closed on a narrow
   * screen and follows the viewport when it crosses the breakpoint, while a
   * deliberate toggle by the user is left alone until the next crossing.
   *
   * `matchMedia` does not exist during SSR, so the decision cannot be made in
   * the initial state without a hydration mismatch. Deferring it to an effect
   * alone is not enough either: the server-rendered HTML is painted before
   * hydration runs, so a phone briefly showed an open 240px drawer and a dark
   * backdrop, then watched them animate away. `hydrated` is what closes that
   * gap — until it flips, the Sidebar renders closed below `md` by CSS alone,
   * which the server can do because the breakpoint is a media query.
   */
  React.useEffect(() => {
    setHydrated(true);
    const query = window.matchMedia(DESKTOP_QUERY);
    const sync = (matches: boolean) => {
      setIsDesktop(matches);
      setOpen(matches && defaultOpen);
    };
    sync(query.matches);
    const onChange = (event: MediaQueryListEvent) => sync(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [defaultOpen]);

  const value = React.useMemo(
    () => ({
      open,
      setOpen,
      hydrated,
      isDesktop,
      toggle: () => setOpen((v) => !v),
      // Below `md` the sidebar overlays the page, so leaving it open after a
      // navigation hides the destination behind a 240px panel and a full
      // screen backdrop. Above `md` it sits in the flow and should stay put.
      closeIfOverlaying: () => {
        if (!isDesktop) setOpen(false);
      },
    }),
    [open, hydrated, isDesktop],
  );

  return (
    <SidebarContext.Provider value={value}>
      <div className={cn("flex min-h-screen w-full", className)} {...props}>
        {children}
        {/*
          Backdrop for the overlaying mobile sidebar. It is a real button so it
          is reachable by keyboard and announced, rather than a bare div — and
          it is not rendered at all above the breakpoint. Hiding it with
          `md:hidden` alone would leave the element in the DOM on desktop,
          where it has no meaning.
        */}
        {open && hydrated && !isDesktop && (
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-20 bg-foreground/40 md:hidden"
          />
        )}
      </div>
    </SidebarContext.Provider>
  );
}

export function Sidebar({ className, children, ...props }: React.HTMLAttributes<HTMLElement>) {
  const { open, hydrated } = useSidebar();
  return (
    <aside
      data-state={open ? "expanded" : "collapsed"}
      className={cn(
        "top-0 z-30 flex h-screen shrink-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200",
        // Overlays the content below md, sits in the flow from md up. Both are
        // variant-prefixed so the two `position` values never collide.
        "max-md:fixed max-md:inset-y-0 max-md:left-0 md:sticky",
        // `invisible` (not just w-0) when closed on a phone: a zero-width
        // overflow-hidden element still keeps its buttons in the tab order, so
        // keyboard users were tabbing through five nav items they could not see.
        open ? "w-60 max-md:shadow-xl" : "w-0 max-md:invisible md:w-14 md:visible",
        // Before hydration the open state is the SSR default, which on a phone
        // meant painting the drawer and then animating it shut. Below `md` it
        // is forced closed by CSS until the client has decided, and the width
        // transition is suppressed so the correction is not animated either.
        !hydrated && "max-md:w-0 max-md:invisible max-md:shadow-none max-md:transition-none",
        className,
      )}
      {...props}
    >
      {children}
    </aside>
  );
}

export function SidebarHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-2 p-3", className)} {...props} />;
}

export function SidebarContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex min-h-0 flex-1 flex-col gap-2 overflow-auto p-2", className)} {...props} />
  );
}

export function SidebarFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-auto flex flex-col gap-2 p-3", className)} {...props} />;
}

export function SidebarGroup({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1 py-1", className)} {...props} />;
}

export function SidebarGroupLabel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const { open } = useSidebar();
  if (!open) return null;
  return (
    <div
      className={cn(
        "px-2 py-1 text-xs font-medium uppercase tracking-wider text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function SidebarMenu({ className, ...props }: React.HTMLAttributes<HTMLUListElement>) {
  return <ul className={cn("flex w-full flex-col gap-1", className)} {...props} />;
}

export function SidebarMenuItem({ className, ...props }: React.HTMLAttributes<HTMLLIElement>) {
  return <li className={cn("relative", className)} {...props} />;
}

export const SidebarMenuButton = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { isActive?: boolean; tooltip?: string }
>(({ className, isActive, tooltip, children, onClick, ...props }, ref) => {
  const { open, closeIfOverlaying } = useSidebar();
  return (
    <button
      ref={ref}
      onClick={(event) => {
        onClick?.(event);
        // Navigating on a phone used to leave the overlay and its backdrop
        // covering the page the user had just asked for, with the header's
        // toggle painted underneath the backdrop and therefore unreachable.
        closeIfOverlaying();
      }}
      title={!open ? tooltip : undefined}
      data-active={isActive}
      // The active nav item was signalled by background colour alone.
      aria-current={isActive ? "page" : undefined}
      className={cn(
        "flex w-full items-center gap-2.5 overflow-hidden rounded-md px-2.5 py-2 text-left text-sm outline-none transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-ring data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium [&_svg]:size-4 [&_svg]:shrink-0",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
});
SidebarMenuButton.displayName = "SidebarMenuButton";

export function SidebarInset({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex min-w-0 flex-1 flex-col", className)} {...props} />;
}

export function SidebarTrigger({ className, ...props }: React.ComponentProps<typeof Button>) {
  const { toggle } = useSidebar();
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label="Toggle sidebar"
      className={cn("h-8 w-8", className)}
      {...props}
    >
      <PanelLeft />
    </Button>
  );
}
