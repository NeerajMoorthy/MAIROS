import { TaskVisualizer } from "@/components/TaskVisualizer";

export const metadata = { title: "Tasks" };

/** How agents divide the work, with every agent run across all projects under it. */
export default function TasksPage() {
  return (
    <div className="h-[calc(100vh-3.5rem)] overflow-auto">
      <div className="border-b px-4 py-4 sm:px-6">
        <h1 className="text-xl font-semibold">Tasks</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          How the agents share the work. Pick a run below to light its agents and see its live
          pipeline trace.
        </p>
      </div>
      <div className="px-4 py-6 sm:px-6">
        <TaskVisualizer />
      </div>
    </div>
  );
}
