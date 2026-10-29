"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BrainCircuit,
  FlaskConical,
  FolderKanban,
  PanelsTopLeft,
  ScrollText,
  Settings,
} from "lucide-react";

import { SystemNotice } from "@/components/SystemNotice";
import { UserMenu } from "@/components/UserMenu";
import { AmbientBackground } from "@/components/ui/AmbientBackground";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { getActiveProjectId, setActiveProjectId } from "@/lib/activeProject";
import { api } from "@/lib/api";
import { AUTH_ENABLED } from "@/lib/config";
import { useHealth } from "@/lib/useHealth";

/** The active project's id, if the current route is inside a project. */
function currentProjectId(pathname: string): string | null {
  const match = pathname.match(/^\/projects\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

interface NavItem {
  label: string;
  icon: typeof FolderKanban;
  /** Global routes have an href; project routes a path below /projects/{id}. */
  href?: string;
  projectPath?: string;
  isActive: (pathname: string) => boolean;
}

const inProject = (pathname: string) => /^\/projects\/[^/]+/.test(pathname);
const inPatents = (pathname: string) => /^\/projects\/[^/]+\/patents/.test(pathname);

const NAV: NavItem[] = [
  { label: "Projects", icon: FolderKanban, href: "/", isActive: (pathname) => pathname === "/" },
  {
    // The Knowledge Graph is one of the Workspace's tabs, so it has no entry of its own.
    label: "Workspace",
    icon: PanelsTopLeft,
    projectPath: "",
    isActive: (pathname) => inProject(pathname) && !inPatents(pathname),
  },
  {
    label: "Patents",
    icon: ScrollText,
    projectPath: "/patents",
    isActive: (pathname) => inPatents(pathname),
  },
  { label: "Tasks", icon: Activity, href: "/tasks", isActive: (pathname) => pathname.startsWith("/tasks") },
  {
    label: "Evaluation",
    icon: FlaskConical,
    href: "/evaluation",
    isActive: (pathname) => pathname.startsWith("/evaluation"),
  },
  {
    label: "Settings",
    icon: Settings,
    href: "/settings",
    isActive: (pathname) => pathname.startsWith("/settings"),
  },
];

/** Routes rendered without the app chrome. */
const BARE_ROUTES = ["/sign-in"];

/** Application chrome: sidebar navigation, ambient background, plus status indicators. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { health, offline } = useHealth();
  const urlProjectId = currentProjectId(pathname);

  const [rememberedProjectId, setRememberedProjectId] = useState<string | null>(null);

  useEffect(() => {
    if (urlProjectId) {
      setActiveProjectId(urlProjectId);
      setRememberedProjectId(urlProjectId);
    } else {
      setRememberedProjectId(getActiveProjectId());
    }
  }, [urlProjectId]);

  /**
   * The project a project-scoped link should open: the one on screen, else
   * the last one used, else the newest. `null` sends the user to pick one.
   */
  const resolveProjectId = useCallback(async (): Promise<string | null> => {
    const known = urlProjectId ?? rememberedProjectId;
    if (known) return known;
    try {
      const projects = await api.listProjects();
      const first = projects[0]?.id ?? null;
      if (first) {
        setActiveProjectId(first);
        setRememberedProjectId(first);
      }
      return first;
    } catch {
      return null;
    }
  }, [urlProjectId, rememberedProjectId]);

  const navigate = useCallback(
    async (item: NavItem) => {
      if (item.href) {
        router.push(item.href);
        return;
      }
      const projectId = await resolveProjectId();
      router.push(projectId ? `/projects/${projectId}${item.projectPath ?? ""}` : "/");
    },
    [router, resolveProjectId],
  );

  if (BARE_ROUTES.some((route) => pathname.startsWith(route))) {
    return (
      <>
        <AmbientBackground />
        <main className="relative min-h-screen">{children}</main>
      </>
    );
  }

  const activeItem = NAV.find((item) => item.isActive(pathname));

  return (
    <SidebarProvider>
      <div className="print:hidden">
        <AmbientBackground />
      </div>

      <Sidebar className="border-r border-frozen/15 bg-black-iris/90 backdrop-blur-xl print:hidden">
        <SidebarHeader className="border-b border-frozen/10">
          <div className="flex items-center gap-2 px-1">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-frozen/30 bg-black-iris text-frozen shadow-[0_0_15px_rgba(160,189,219,0.2)]">
              <BrainCircuit className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold tracking-wide text-foreground">MAIROS</p>
              <p className="truncate text-xs text-frozen/80">Research Orchestrator</p>
            </div>
          </div>
        </SidebarHeader>

        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel className="text-xs uppercase tracking-wider text-muted-foreground/80">
              Navigate
            </SidebarGroupLabel>
            <SidebarMenu>
              {NAV.map((item) => {
                const active = item === activeItem;
                const Icon = item.icon;
                return (
                  <SidebarMenuItem key={item.label}>
                    <SidebarMenuButton
                      isActive={active}
                      tooltip={item.label}
                      onClick={() => void navigate(item)}
                      className={`transition-all duration-200 ${
                        active
                          ? "border-l-2 border-frozen bg-frozen/10 font-medium text-frozen"
                          : "hover:bg-frozen/5 hover:text-foreground"
                      }`}
                    >
                      <Icon className={active ? "text-frozen" : ""} />
                      <span className="truncate">{item.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>

        <SidebarFooter className="space-y-2">
          {AUTH_ENABLED && <UserMenu />}
        </SidebarFooter>
      </Sidebar>

      <SidebarInset className="bg-transparent">
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b border-frozen/15 bg-black-iris/85 px-4 backdrop-blur-md print:hidden">
          <SidebarTrigger className="shrink-0 text-muted-foreground hover:text-foreground" />
          <Link
            href="/"
            className="focus-ring shrink-0 rounded-sm px-0.5 py-1.5 text-sm font-medium text-frozen transition-colors hover:text-foreground hover:underline"
          >
            MAIROS
          </Link>
          <span aria-hidden="true" className="shrink-0 text-muted-foreground">
            /
          </span>
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground/90">
            {activeItem?.label ?? "Workspace"}
          </span>
          <div className="flex min-w-0 shrink items-center gap-2">
            {/* Only once health has answered: before that, "not live" is unknown,
                not false, and the banner used to flash on every page load even
                with a live model configured. */}
            {!offline && health && !health.llm.live && (
              <SystemNotice variant="offline" compact className="max-w-[45vw] sm:max-w-none" />
            )}
          </div>
        </header>

        <main className="min-h-0 flex-1">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
