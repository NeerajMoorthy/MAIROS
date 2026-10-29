"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import {
  Download,
  FlaskConical,
  MessagesSquare,
  Network,
  ScrollText,
  Search,
} from "lucide-react";

import { ChatPanel } from "@/components/ChatPanel";
import { GraphViewer } from "@/components/GraphViewer";
import { ProjectExportDialog } from "@/components/ProjectExportDialog";
import { ProjectOverview } from "@/components/ProjectOverview";
import { SearchUpload } from "@/components/SearchUpload";
import { WorkflowPanel } from "@/components/WorkflowPanel";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { setActiveProjectId } from "@/lib/activeProject";
import { api, type ExampleWorkspaceInfo, type ProjectDetail, type ProjectStats } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

const TABS = [
  { value: "search", label: "Search & Upload", icon: Search },
  { value: "chat", label: "Chat & Q&A", icon: MessagesSquare },
  { value: "workflows", label: "Workflows", icon: FlaskConical },
  { value: "graph", label: "Knowledge Graph", icon: Network },
] as const;

const VALID_TABS: string[] = TABS.map((t) => t.value);

const STATS_POLL_MS = 4000;

const TRIGGER_CLASS =
  "transition-all data-[state=active]:border-b-2 data-[state=active]:border-frozen data-[state=active]:bg-frozen/15 data-[state=active]:text-frozen data-[state=active]:shadow-[0_0_12px_rgba(160,189,219,0.15)]";

/** Observes the ?tab= query parameter dynamically via Next.js navigation hooks. */
function SearchTabWatcher({ onTabChange }: { onTabChange: (tab: string) => void }) {
  const searchParams = useSearchParams();
  const requested = searchParams.get("tab");
  useEffect(() => {
    if (requested && VALID_TABS.includes(requested)) {
      onTabChange(requested);
    }
  }, [requested, onTabChange]);
  return null;
}

export default function ProjectWorkspace() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [tab, setTab] = useState("search");
  const [exportOpen, setExportOpen] = useState(false);
  const [exampleInfo, setExampleInfo] = useState<ExampleWorkspaceInfo | null>(null);
  const exportButton = useRef<HTMLButtonElement>(null);
  const refreshGeneration = useRef(0);

  useEffect(() => {
    if (projectId) setActiveProjectId(projectId);
  }, [projectId]);

  // Synchronize state and browser URL when tab changes
  const handleTabChange = useCallback((newTab: string) => {
    setTab(newTab);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (newTab === "search") {
        url.searchParams.delete("tab");
      } else {
        url.searchParams.set("tab", newTab);
      }
      window.history.replaceState(null, "", url.toString());
    }
  }, []);

  const refresh = useCallback(async () => {
    const generation = ++refreshGeneration.current;
    try {
      const [detail, projectStats] = await Promise.all([
        api.getProject(projectId),
        api.projectStats(projectId).catch(() => null),
      ]);
      if (generation !== refreshGeneration.current) return;
      setProject(detail);
      if (projectStats) setStats(projectStats);
      setWorkspaceError(null);
    } catch (err) {
      if (generation === refreshGeneration.current) {
        setWorkspaceError(describeError(err, "Could not load this workspace."));
      }
    } finally {
      if (generation === refreshGeneration.current) setWorkspaceLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setWorkspaceLoading(true);
    setWorkspaceError(null);
    setProject(null);
    setStats(null);
    void refresh();
  }, [refresh]);

  // Runs start from Workflows, Chat, the Tasks page or another device, and
  // finish on their own, so the header counts are re-read while the page is
  // open. Loading them once left "Tasks running" at 0 during busy runs.
  useEffect(() => {
    let cancelled = false;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      api.projectStats(projectId).then(
        (next) => {
          if (!cancelled) setStats(next);
        },
        () => {},
      );
    }, STATS_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [projectId]);

  // The example project (Settings -> Load example data) gets "Use example"
  // inputs on its workflow cards and topic search.
  const isExample = project !== null && exampleInfo !== null && project.name === exampleInfo.name;
  useEffect(() => {
    let cancelled = false;
    api.exampleWorkspace().then(
      (info) => {
        if (!cancelled) setExampleInfo(info);
      },
      () => {},
    );
    return () => {
      cancelled = true;
    };
  }, []);
  const examples = useMemo(() => {
    if (!isExample || !exampleInfo) return undefined;
    return Object.fromEntries(
      exampleInfo.guide.filter((step) => step.flow).map((step) => [step.flow as string, step.input]),
    );
  }, [isExample, exampleInfo]);
  const exampleTopic = isExample
    ? exampleInfo?.guide.find((step) => step.feature === "Topic search")?.input
    : undefined;

  /**
   * Called when a panel starts a pipeline run. The panel follows the run
   * itself; every run, across projects, is on the Tasks page.
   */
  const handleTaskStarted = useCallback(() => {
    refresh();
  }, [refresh]);

  if (!project) {
    return (
      <div className="mx-auto w-full max-w-6xl p-6 md:p-10">
        {workspaceLoading ? (
          <p role="status" className="text-sm text-muted-foreground">Loading workspace…</p>
        ) : (
          <section role="alert" className="max-w-xl rounded-lg border border-destructive/40 bg-destructive/10 p-5">
            <h1 className="font-semibold">Unable to open this workspace</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {workspaceError ?? "The project could not be loaded."}
            </p>
            <Button
              className="mt-4"
              variant="outline"
              onClick={() => {
                setWorkspaceLoading(true);
                void refresh();
              }}
            >
              Retry
            </Button>
          </section>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <Suspense fallback={null}>
        <SearchTabWatcher onTabChange={setTab} />
      </Suspense>

      <div className="shrink-0 space-y-4 border-b border-frozen/15 bg-black-iris/60 px-4 py-4 backdrop-blur-md sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold tracking-tight text-foreground">
              {project.name}
            </h1>
            {project.description && (
              <p className="truncate text-sm text-frozen/80">{project.description}</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm" className="border-frozen/30">
              <Link href={`/projects/${projectId}/patents`}>
                <ScrollText /> Patents
              </Link>
            </Button>
            <Button
              ref={exportButton}
              variant="outline"
              size="sm"
              className="border-frozen/30"
              onClick={() => setExportOpen(true)}
            >
              <Download /> Export data
            </Button>
          </div>
        </div>
        <ProjectExportDialog
          projectId={projectId}
          open={exportOpen}
          onOpenChange={setExportOpen}
          returnFocusTo={exportButton}
        />
        {workspaceError && (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
            <span>{workspaceError}</span>
            <Button variant="outline" size="sm" onClick={() => void refresh()}>Retry</Button>
          </div>
        )}
        <ProjectOverview stats={stats} />
      </div>

      <Tabs
        value={tab}
        onValueChange={handleTabChange}
        className="flex min-h-0 flex-1 flex-col"
      >
        <div className="shrink-0 overflow-x-auto px-4 pt-4 [scrollbar-width:none] sm:px-6 [&::-webkit-scrollbar]:hidden">
          <TabsList className="relative w-max rounded-xl border border-frozen/20 bg-black-iris/85 p-1 backdrop-blur-md">
            {TABS.map(({ value, label, icon: Icon }) => (
              <TabsTrigger key={value} value={value} className={TRIGGER_CLASS}>
                <Icon /> {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <TabsContent value="search" className="min-h-0 flex-1 overflow-auto px-4 pb-6 sm:px-6">
          <SearchUpload
            projectId={projectId}
            documents={project?.documents ?? []}
            onTaskStarted={handleTaskStarted}
            onChanged={refresh}
            exampleTopic={exampleTopic}
          />
        </TabsContent>

        <TabsContent value="chat" className="mt-0 min-h-0 flex-1">
          <ChatPanel projectId={projectId} />
        </TabsContent>

        <TabsContent value="workflows" className="min-h-0 flex-1 overflow-auto px-4 pb-6 sm:px-6">
          <WorkflowPanel projectId={projectId} examples={examples} />
        </TabsContent>

        <TabsContent value="graph" className="mt-0 min-h-0 flex-1">
          <GraphViewer projectId={projectId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
