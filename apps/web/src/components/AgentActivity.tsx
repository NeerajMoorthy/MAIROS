"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, Loader2 } from "lucide-react";

import { PipelineTrace } from "@/components/PipelineTrace";
import { TaskAnswer, WorkflowSections } from "@/components/TaskResultView";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { STAGES, api, humanise, type Task } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

interface Props {
  projectId?: string;
  selectedTaskId?: string | null;
  onSelect?: (taskId: string) => void;
  onSettled?: () => void;
}

const POLL_MS = 1500;

const AGENT_COLOURS: Record<string, string> = {
  orchestrator: "bg-primary",
  literature: "bg-sky-500",
  indexer: "bg-violet-500",
  loader: "bg-violet-500",
  retriever: "bg-cyan-500",
  analysis: "bg-amber-500",
  knowledge_graph: "bg-emerald-500",
  citation: "bg-rose-500",
  synthesis: "bg-indigo-500",
};

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
      <p className="line-clamp-2 text-sm font-medium">{task.request}</p>
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

/** Tab (c): live view of which agent ran, when, and what it produced. */
export function AgentActivity({ projectId, selectedTaskId, onSelect, onSettled }: Props) {
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
    // Below `lg` the two cards stack and the page scrolls; giving both a share
    // of one fixed height clipped the detail card on phones.
    <div className="grid grid-cols-1 gap-4 py-2 lg:h-full lg:min-h-0 lg:grid-cols-[minmax(18rem,0.85fr)_minmax(0,2fr)]">
      <Card className="flex min-w-0 flex-col overflow-hidden lg:min-h-0">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Runs</CardTitle>
        </CardHeader>
        <CardContent className="max-h-[40vh] min-h-0 flex-1 p-0 lg:max-h-none">
          <ScrollArea className="h-full px-4 pb-4">
            {pollError && (
              <p role="alert" className="my-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
                {pollError}
              </p>
            )}
            {loading ? (
              <p role="status" className="py-8 text-center text-sm text-muted-foreground">
                Loading…
              </p>
            ) : tasks.length === 0 ? (
              pollError ? null : (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No agent runs yet. Upload a PDF or search a topic to start one.
                </p>
              )
            ) : (
              <div className="space-y-2">
                {tasks.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    selected={selectedId === task.id}
                    onClick={() => {
                      setSelected(task);
                      onSelect?.(task.id);
                    }}
                  />
                ))}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      <Card className="flex min-w-0 flex-col overflow-hidden lg:min-h-0">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Pipeline detail</CardTitle>
        </CardHeader>
        <CardContent className="min-h-0 flex-1 p-0">
          <ScrollArea className="h-full px-6 pb-6">
            {!selected ? (
              <p className="py-16 text-center text-sm text-muted-foreground">
                Select a run to inspect it.
              </p>
            ) : (
              // Keyed by run, so nothing from one run's detail (expanded
              // passages, disclosure state) carries over to the next.
              <div key={selected.id} className="space-y-6">
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

                <div>
                  <h4 className="mb-3 text-sm font-medium">
                    Algorithm trace — Router → Retrieval/Analysis → Indexing → Knowledge Graph → Citation → Synthesis
                  </h4>
                  <PipelineTrace task={selected} />
                </div>

                <div>
                  <h4 className="mb-3 text-sm font-medium">Agent activity log</h4>
                  {selected.events.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No events yet.</p>
                  ) : (
                    <ol className="relative space-y-4 border-l pl-6">
                      {selected.events.map((event, index) => (
                        <li key={`${event.timestamp}-${index}`} className="relative">
                          <span
                            aria-hidden="true"
                            className={`absolute -left-[1.6rem] top-1 h-3 w-3 rounded-full ring-4 ring-background ${
                              event.status === "failed"
                                ? "bg-destructive"
                                : (AGENT_COLOURS[event.agent_name] ?? "bg-muted-foreground")
                            }`}
                          />
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium">{humanise(event.agent_name)}</span>
                            <Badge variant="outline" className="text-[10px]">
                              {humanise(event.stage)}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {new Date(event.timestamp).toLocaleTimeString()}
                            </span>
                          </div>
                          <p className="mt-1 break-words text-sm text-muted-foreground">{event.message}</p>
                        </li>
                      ))}
                    </ol>
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
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}

export default AgentActivity;
