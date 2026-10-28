"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, Loader2 } from "lucide-react";

import { OrchestrationTree } from "@/components/OrchestrationTree";
import { TaskAnswer, WorkflowSections } from "@/components/TaskResultView";
import { Badge } from "@/components/ui/badge";
import { STAGES, api, humanise, type Task } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

interface Props {
  projectId?: string;
  selectedTaskId?: string | null;
  onSelect?: (taskId: string) => void;
  onSettled?: () => void;
  /** The run on show changed (or its flow became known); `null` when there is none. */
  onRunChange?: (task: Task | null) => void;
}

const POLL_MS = 1500;

export function StatusBadge({ status }: { status: Task["status"] }) {
  switch (status) {
    case "completed":
      return (
        <Badge variant="success">
          <CheckCircle2 className="h-3 w-3" /> completed
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="destructive">
          <AlertTriangle className="h-3 w-3" /> failed
        </Badge>
      );
    case "running":
      return (
        <Badge>
          <Loader2 className="h-3 w-3 animate-spin" /> running
        </Badge>
      );
    default:
      return (
        <Badge variant="secondary">
          <Clock className="h-3 w-3" /> queued
        </Badge>
      );
  }
}

/**
 * One run in the list. The flow, the start time and a short run id are shown
 * because the same prompt submitted twice is two genuine runs: with only the
 * prompt text on each row they looked like one run listed twice.
 */
function TaskRow({ task, selected, onClick }: { task: Task; selected: boolean; onClick: () => void }) {
  const flow = task.flow ?? task.result?.routing?.flow ?? null;
  return (
    <button
      type="button"
      onClick={onClick}
      // aria-current marks the row the detail pane is showing, which is
      // otherwise conveyed by colour alone.
      aria-current={selected ? "true" : undefined}
      className={`focus-ring w-full rounded-lg border p-3 text-left transition-colors hover:bg-accent/50 ${
        selected ? "border-primary bg-accent/40" : ""
      }`}
    >
      <p className="line-clamp-2 text-sm font-medium [overflow-wrap:anywhere]">{task.request}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <StatusBadge status={task.status} />
        {flow && (
          <Badge variant="outline" className="text-[10px]">
            {flow}
          </Badge>
        )}
        <span className="ml-auto shrink-0 text-xs text-muted-foreground">
          <span className="font-mono">#{task.id.slice(0, 6)}</span> ·{" "}
          {new Date(task.created_at).toLocaleTimeString()}
        </span>
      </div>
    </button>
  );
}

/** Live view of every agent run: which agent ran, when, and what it produced. */
export function AgentActivity({ projectId, selectedTaskId, onSelect, onSettled, onRunChange }: Props) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selected, setSelected] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [pollError, setPollError] = useState<string | null>(null);
  const settledRef = useRef<Set<string>>(new Set());
  // Each poll is numbered; a response is applied only if no later poll has
  // been started since. A slow response arriving after a fast one used to
  // put the older task list back on screen for a tick.
  const pollGeneration = useRef(0);

  const selectedId = selectedTaskId ?? selected?.id ?? null;

  const poll = useCallback(async () => {
    const generation = ++pollGeneration.current;
    try {
      const list = await api.listTasks(projectId);
      if (generation !== pollGeneration.current) return;
      setTasks(list);
      setPollError(null);

      const current = selectedId ? (list.find((t) => t.id === selectedId) ?? list[0]) : list[0];
      if (current) {
        setSelected(current);
        if (selectedId !== current.id) onSelect?.(current.id);
        // Refresh the parent's stats once, the first time a run settles.
        if (
          (current.status === "completed" || current.status === "failed") &&
          !settledRef.current.has(current.id)
        ) {
          settledRef.current.add(current.id);
          onSettled?.();
        }
      } else {
        // A project change or deleted task must not leave another project's
        // previous detail visible beside the new (empty) task list.
        setSelected(null);
      }
    } catch (err) {
      if (generation === pollGeneration.current) {
        setPollError(describeError(err, "Could not load agent runs. Retrying…"));
      }
    } finally {
      if (generation === pollGeneration.current) setLoading(false);
    }
  }, [projectId, selectedId, onSelect, onSettled]);

  // Polling replaces `selected` every tick; tell the parent only when the run
  // or its flow actually changes, so it can light that flow's agents.
  const shownFlow = selected ? (selected.flow ?? selected.result?.routing?.flow ?? null) : null;
  const onRunChangeRef = useRef(onRunChange);
  onRunChangeRef.current = onRunChange;
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  useEffect(() => {
    onRunChangeRef.current?.(selectedRef.current);
  }, [selected?.id, shownFlow]);

  useEffect(() => {
    void poll();
    const timer = setInterval(poll, POLL_MS);
    return () => clearInterval(timer);
  }, [poll]);

  const progress = selected
    ? Math.max(
        6,
        ((STAGES.indexOf(selected.current_stage as (typeof STAGES)[number]) + 1) / STAGES.length) * 100,
      )
    : 0;

  return (
    // Shown under the agent map on Tasks: the runs as one scrolling row, and
    // the chosen run's trace below it, rather than two side-by-side panels.
    <div className="space-y-5">
      <div>
        <h3 className="mb-2 text-sm font-medium">Runs</h3>
        {pollError && (
          <p role="alert" className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
            {pollError}
          </p>
        )}
        {loading ? (
          <p role="status" className="py-4 text-sm text-muted-foreground">
            Loading…
          </p>
        ) : tasks.length === 0 ? (
          pollError ? null : (
            <p className="py-4 text-sm text-muted-foreground">
              No agent runs yet. Upload a PDF or search a topic to start one.
            </p>
          )
        ) : (
          <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-2">
            {tasks.map((task) => (
              <div key={task.id} className="w-64 shrink-0 sm:w-72">
                <TaskRow
                  task={task}
                  selected={selectedId === task.id}
                  onClick={() => {
                    setSelected(task);
                    onSelect?.(task.id);
                  }}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {selected && (
        // Keyed by run, so nothing from one run's detail (expanded passages,
        // disclosure state) carries over to the next.
        <div key={selected.id} className="min-w-0 space-y-6 rounded-xl border border-frozen/10 bg-black-iris/50 p-4 sm:p-5">
          <div>
            <h3 className="font-medium">{selected.request}</h3>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusBadge status={selected.status} />
              {selected.current_stage !== selected.status && (
                <Badge variant="outline">{humanise(selected.current_stage)}</Badge>
              )}
              {selected.result?.routing && (
                <Badge variant="secondary">flow: {selected.result.routing.flow}</Badge>
              )}
              <span className="font-mono text-xs text-muted-foreground">run #{selected.id.slice(0, 6)}</span>
            </div>
            {selected.result?.routing?.reason && (
              <p className="mt-2 text-xs text-muted-foreground">
                Router ({selected.result.routing.decided_by}): {selected.result.routing.reason}
              </p>
            )}
          </div>

          <div
            className="h-2 w-full overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-label="Pipeline progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(progress)}
          >
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                selected.status === "failed" ? "bg-destructive" : "bg-primary"
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>

          <div className="min-w-0 overflow-x-auto">
            <h4 className="mb-3 text-sm font-medium">
              Orchestration tree — the Orchestrator assigns each step to an agent
            </h4>
            {selected.events.length === 0 ? (
              <p className="text-sm text-muted-foreground">No events yet.</p>
            ) : (
              <OrchestrationTree task={selected} />
            )}
          </div>

          {selected.error && (
            <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-4">
              <p className="text-sm font-medium">Workflow failed</p>
              <p className="mt-1 break-words text-sm text-muted-foreground">{selected.error}</p>
            </div>
          )}

          {selected.result && (
            <>
              <WorkflowSections result={selected.result} />
              <TaskAnswer result={selected.result} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default AgentActivity;
