import { CheckCircle2, CircleDashed, Loader2, MinusCircle, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { PIPELINE_STAGES, humanise, type Task, type TaskEvent } from "@/lib/api";

type StageStatus = "pending" | "running" | "completed" | "failed" | "skipped";

const STATUS_STYLE: Record<StageStatus, { icon: typeof CheckCircle2; classes: string; label: string }> = {
  pending: { icon: CircleDashed, classes: "border-muted-foreground/30 text-muted-foreground", label: "Pending" },
  running: { icon: Loader2, classes: "border-primary bg-primary/10 text-primary", label: "Running" },
  completed: { icon: CheckCircle2, classes: "border-success bg-success/10 text-success", label: "Completed" },
  failed: { icon: XCircle, classes: "border-destructive bg-destructive/10 text-destructive", label: "Failed" },
  skipped: { icon: MinusCircle, classes: "border-muted-foreground/15 text-muted-foreground/50", label: "Not in this flow" },
};

/** Latest event for any agent in `agents`, or undefined if none has run yet. */
function latestEventFor(events: TaskEvent[], agents: readonly string[]): TaskEvent | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    if (agents.includes(events[i].agent_name)) return events[i];
  }
  return undefined;
}

function statusOf(event: TaskEvent | undefined, taskFailed: boolean): StageStatus {
  if (!event) return "pending";
  if (event.status === "failed") return "failed";
  if (event.status === "completed") return "completed";
  // A stage's own event may say "running" even after the task later failed
  // elsewhere — that stage itself still finished, it just isn't "completed"
  // in the schema, so treat a trailing running event on a failed task as
  // ambiguous rather than claiming it finished.
  return taskFailed ? "failed" : "running";
}

interface Props {
  task: Task | null;
  /** Compact renders a horizontal stepper with no per-stage detail (used inline in SearchUpload). */
  compact?: boolean;
}

/**
 * The ordered Algorithm Trace: Router -> Retrieval/Analysis -> Indexing ->
 * Knowledge Graph -> Citation -> Synthesis, each stage's status derived only
 * from this task's real events — never fabricated. When the task's routing
 * decision is known (`result.routing.agents`), a stage whose agents are not
 * part of the chosen flow is marked "skipped" instead of stuck pending.
 */
export function PipelineTrace({ task, compact = false }: Props) {
  if (!task) return null;

  const flowAgents: string[] | null = task.result?.routing?.agents ?? null;
  const taskFailed = task.status === "failed";

  const stages = PIPELINE_STAGES.map((stage) => {
    const event = latestEventFor(task.events, stage.agents);
    const inFlow = stage.key === "router" || !flowAgents || stage.agents.some((a) => flowAgents.includes(a));
    const status: StageStatus = !inFlow && !event ? "skipped" : statusOf(event, taskFailed);
    return { ...stage, event, status };
  });

  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-1.5">
        {stages.map((stage, index) => {
          const { icon: Icon, classes } = STATUS_STYLE[stage.status];
          return (
            <div key={stage.key} className="flex items-center gap-1.5">
              <div
                className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${classes}`}
                title={`${stage.label}: ${STATUS_STYLE[stage.status].label}`}
              >
                <Icon className={`h-3 w-3 ${stage.status === "running" ? "animate-spin" : ""}`} />
                {stage.label}
              </div>
              {index < stages.length - 1 && <span className="text-muted-foreground/40">→</span>}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {stages.map((stage) => {
        const { icon: Icon, classes, label } = STATUS_STYLE[stage.status];
        return (
          <div key={stage.key} className={`flex items-start gap-3 rounded-lg border p-2.5 ${classes}`}>
            <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${stage.status === "running" ? "animate-spin" : ""}`} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-foreground">{stage.label}</span>
                <Badge
                  variant={
                    stage.status === "completed"
                      ? "success"
                      : stage.status === "failed"
                        ? "destructive"
                        : stage.status === "running"
                          ? "default"
                          : "secondary"
                  }
                  className="text-[10px]"
                >
                  {label}
                </Badge>
                {stage.event && (
                  <span className="min-w-0 break-words text-xs text-muted-foreground">
                    {humanise(stage.event.agent_name)} ·{" "}
                    {new Date(stage.event.timestamp).toLocaleTimeString()}
                  </span>
                )}
              </div>
              {stage.event?.message && (
                <p className="mt-0.5 break-words text-xs text-muted-foreground">{stage.event.message}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default PipelineTrace;
