import { AgentActivity } from "@/components/AgentActivity";
import { AgentNetwork3D } from "@/components/AgentNetwork3D";

export const metadata = { title: "Tasks" };

/** How agents divide the work, then every agent run across all projects. */
export default function TasksPage() {
  return (
    <div className="h-[calc(100vh-3.5rem)] overflow-auto">
      <div className="border-b px-4 py-4 sm:px-6">
        <h1 className="text-xl font-semibold">Tasks</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          How the agents share the work, and every multi-agent run across all projects with its
          live pipeline trace.
        </p>
      </div>
      <div className="space-y-6 px-4 py-6 sm:px-6">
        <AgentNetwork3D />
        <section aria-labelledby="agent-activity-title">
          <h2 id="agent-activity-title" className="mb-3 text-lg font-semibold">
            Agent Activity
          </h2>
          {/* A fixed height on wide screens, where the run list and detail sit side by side. */}
          <div className="lg:h-[640px]">
            <AgentActivity />
          </div>
        </section>
      </div>
    </div>
  );
}
