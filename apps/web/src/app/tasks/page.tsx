import { AgentActivity } from "@/components/AgentActivity";

export const metadata = { title: "Agent Activity" };

/** Global view of every agent run across all projects. */
export default function TasksPage() {
  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <div className="shrink-0 border-b px-4 py-4 sm:px-6">
        <h1 className="text-xl font-semibold">Agent Activity</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every multi-agent run, across all projects, with its live pipeline trace.
        </p>
      </div>
      {/* Scrolls below `lg`, where the run list and detail stack. */}
      <div className="min-h-0 flex-1 overflow-auto px-4 pb-6 sm:px-6 lg:overflow-hidden">
        <AgentActivity />
      </div>
    </div>
  );
}
