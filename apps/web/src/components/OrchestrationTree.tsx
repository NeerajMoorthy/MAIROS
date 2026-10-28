import { CheckCircle2, CircleDashed, GitBranch, Loader2, MinusCircle, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { humanise, type Task, type TaskEvent } from "@/lib/api";

type AgentStatus = "waiting" | "running" | "done" | "failed" | "not_reached";

const STATUS: Record<AgentStatus, { icon: typeof CheckCircle2; label: string; classes: string }> = {
  waiting: { icon: CircleDashed, label: "Waiting", classes: "border-muted-foreground/30 text-muted-foreground" },
  running: { icon: Loader2, label: "Running", classes: "border-primary text-primary" },
  done: { icon: CheckCircle2, label: "Done", classes: "border-success text-success" },
  failed: { icon: XCircle, label: "Failed", classes: "border-destructive text-destructive" },
  not_reached: { icon: MinusCircle, label: "Not reached", classes: "border-muted-foreground/20 text-muted-foreground/60" },
};

const PIPELINE_PREFIX = "Pipeline: ";

/**
 * The agents this run's flow assigns, in order. Taken from the router's
 * decision once the run has finished, and before that from the orchestrator's
 * own "Pipeline: a → b → c" event, so the tree is complete while it runs.
 */
export function flowAgents(task: Task): string[] {
  const decided = task.result?.routing?.agents;
  if (decided?.length) return decided;
  const announced = task.events.find(
    (e) => e.agent_name === "orchestrator" && e.message.startsWith(PIPELINE_PREFIX),
  );
  if (announced) {
    return announced.message.slice(PIPELINE_PREFIX.length).split(" → ").map((name) => name.trim());
  }
  // An old run without the announcement: the agents in the order they spoke.
  return [...new Set(task.events.map((e) => e.agent_name).filter((name) => name !== "orchestrator"))];
}

function statusOf(agent: string, agents: string[], events: TaskEvent[], task: Task): AgentStatus {
  const own = events.filter((e) => e.agent_name === agent);
  if (own.some((e) => e.status === "failed")) return "failed";
  if (own.length === 0) {
    return task.status === "completed" || task.status === "failed" ? "not_reached" : "waiting";
  }
  if (task.status !== "running" && task.status !== "queued") return "done";
  // Still running: this agent is the one at work if no later agent has spoken.
  const later = agents.slice(agents.indexOf(agent) + 1);
  return events.some((e) => later.includes(e.agent_name)) ? "done" : "running";
}

function StatusIcon({ status }: { status: AgentStatus }) {
  const { icon: Icon, label } = STATUS[status];
  return (
    <Icon
      aria-label={label}
      className={`h-3.5 w-3.5 shrink-0 ${status === "running" ? "animate-spin" : ""}`}
    />
  );
}

function time(event: TaskEvent) {
  return new Date(event.timestamp).toLocaleTimeString();
}

/**
 * A run as a tree: the Orchestrator at the root, with its routing decision and
 * its own steps, and one branch per agent the flow assigned — each a table
 * headed by the agent, listing the work that agent reported, in order.
 * Everything shown comes from the run's recorded events; nothing is inferred
 * except the agent's status, which is derived from those events.
 */
export function OrchestrationTree({ task }: { task: Task }) {
  const agents = flowAgents(task);
  const routing = task.result?.routing;
  const rootEvents = task.events.filter((e) => e.agent_name === "orchestrator");
  const rootFailed = rootEvents.some((e) => e.status === "failed");
  const rootStatus: AgentStatus = rootFailed
    ? "failed"
    : task.status === "completed"
      ? "done"
      : task.status === "failed"
        ? "failed"
        : "running";

  return (
    <figure aria-label="Orchestration tree" className="overflow-x-auto pb-2">
      <div className="mx-auto w-fit min-w-full">
        {/* Root: the Orchestrator. */}
        <div className="flex justify-center">
          <div className={`w-full max-w-xl rounded-xl border-2 bg-card p-3 shadow-sm ${STATUS[rootStatus].classes}`}>
            <div className="flex flex-wrap items-center gap-2">
              <GitBranch className="h-4 w-4 text-primary" aria-hidden="true" />
              <h4 className="text-sm font-semibold text-foreground">Orchestrator</h4>
              <StatusIcon status={rootStatus} />
              {(routing?.flow ?? task.flow) && (
                <Badge variant="secondary" className="text-[10px]">
                  flow: {routing?.flow ?? task.flow}
                </Badge>
              )}
              <span className="ml-auto text-xs text-muted-foreground">
                assigns {agents.length} agent{agents.length === 1 ? "" : "s"}
              </span>
            </div>
            {routing?.reason && (
              <p className="mt-1.5 text-xs text-muted-foreground">
                Router ({routing.decided_by}): {routing.reason}
              </p>
            )}
            {rootEvents.length > 0 && (
              <ol className="mt-2 space-y-0.5 border-t pt-2 text-xs text-muted-foreground">
                {rootEvents.map((event, index) => (
                  <li key={`${event.timestamp}-${index}`} className="flex gap-2">
                    <span className="shrink-0 tabular-nums">{time(event)}</span>
                    <span className="break-words">{event.message}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>

        {agents.length > 0 && (
          <>
            {/* Trunk and branches. */}
            <div aria-hidden="true" className="mx-auto h-5 w-px bg-border" />
            <ol className="flex gap-3">
              {agents.map((agent, index) => {
                const status = statusOf(agent, agents, task.events, task);
                const own = task.events.filter((e) => e.agent_name === agent);
                return (
                  <li key={`${agent}-${index}`} className="relative flex min-w-[13rem] flex-1 flex-col pt-5">
                    {/* The horizontal bar spans the siblings; each branch drops from it. */}
                    <span
                      aria-hidden="true"
                      className={`absolute top-0 h-px bg-border ${
                        agents.length === 1
                          ? "hidden"
                          : index === 0
                            ? "left-1/2 right-[-0.375rem]"
                            : index === agents.length - 1
                              ? "left-[-0.375rem] right-1/2"
                              : "left-[-0.375rem] right-[-0.375rem]"
                      }`}
                    />
                    <span aria-hidden="true" className="absolute left-1/2 top-0 h-5 w-px bg-border" />
                    <table className={`w-full overflow-hidden rounded-lg border-2 bg-card text-left text-xs ${STATUS[status].classes}`}>
                      <caption className="sr-only">
                        Step {index + 1}: {humanise(agent)}, {STATUS[status].label}
                      </caption>
                      <thead>
                        <tr className="border-b bg-muted/40">
                          <th scope="col" colSpan={2} className="px-2.5 py-2">
                            <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                              <span className="text-xs font-normal text-muted-foreground">{index + 1}.</span>
                              {humanise(agent)}
                              <span className="ml-auto flex items-center gap-1 text-[11px] font-normal">
                                <StatusIcon status={status} />
                                {STATUS[status].label}
                              </span>
                            </span>
                          </th>
                        </tr>
                      </thead>
                      <tbody className="text-muted-foreground">
                        {own.length === 0 ? (
                          <tr>
                            <td colSpan={2} className="px-2.5 py-2 italic">
                              {status === "waiting" ? "Not started yet" : "No work reported"}
                            </td>
                          </tr>
                        ) : (
                          own.map((event, row) => (
                            <tr key={`${event.timestamp}-${row}`} className="border-t first:border-t-0 align-top">
                              <td className="whitespace-nowrap px-2.5 py-1.5 tabular-nums">{time(event)}</td>
                              <td className="break-words px-2.5 py-1.5 text-foreground/90">{event.message}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </div>
    </figure>
  );
}

export default OrchestrationTree;
