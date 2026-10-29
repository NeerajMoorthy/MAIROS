"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  FlaskConical,
  GitCompare,
  Lightbulb,
  Loader2,
  Play,
  Compass,
  FileSearch,
  Library,
  ScrollText,
  SearchX,
  Sparkles,
} from "lucide-react";

import { PatentDisclaimer } from "@/components/patents/PatentDisclaimer";
import { PipelineTrace } from "@/components/PipelineTrace";
import { WorkflowSections } from "@/components/TaskResultView";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, type Task } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

interface Props {
  projectId: string;
  onTaskStarted?: (taskId: string) => void;
  /** In the example project: an input per flow with a known answer (Settings). */
  examples?: Record<string, string>;
}

interface WorkflowSpec {
  flow: string;
  title: string;
  icon: typeof GitCompare;
  description: string;
  placeholder: string;
  defaultQuestion: string;
  /** Takes a pasted description rather than a one-line question. */
  multiline?: boolean;
}

/** Below this, a "description" is too short for the intake step to read. */
const MIN_DESCRIPTION_CHARS = 200;

const WORKFLOWS: WorkflowSpec[] = [
  {
    flow: "project",
    title: "Review my project",
    icon: FileSearch,
    description:
      "Paste your project description. MAIROS reads it into a brief, searches arXiv, OpenAlex and Semantic Scholar, contrasts what it finds, lists the gaps those papers state, and checks each of your stated contributions against them. It reports coverage in what was searched — never a novelty verdict.",
    placeholder:
      "Describe your project: the problem, the methods you use, the data, and what you propose or build (at least a few sentences).",
    defaultQuestion: "",
    multiline: true,
  },
  {
    flow: "compare",
    title: "Compare papers",
    icon: GitCompare,
    description:
      "Contrasts the documents this project has indexed and returns a table where every cell carries the passage it came from.",
    placeholder: "What should the comparison focus on?",
    defaultQuestion: "Compare the methods and results of the indexed papers",
  },
  {
    flow: "gaps",
    title: "Detect research gaps",
    icon: SearchX,
    description:
      "Finds open problems the sources themselves state, quoting the sentence behind each one, plus structural signals from the knowledge graph.",
    placeholder: "Which area should be examined for gaps?",
    defaultQuestion: "What open problems and limitations remain in this literature?",
  },
  {
    flow: "hypothesis",
    title: "Generate hypotheses",
    icon: Lightbulb,
    description:
      "Detects gaps first, then proposes a falsifiable hypothesis for each one — every proposal keeps the citation of the gap it came from.",
    placeholder: "What direction should the hypotheses explore?",
    defaultQuestion: "What hypotheses follow from the gaps in this literature?",
  },
  {
    flow: "experiment",
    title: "Design experiments",
    icon: FlaskConical,
    description:
      "Runs the full chain — gaps, then hypotheses, then a protocol for each: objective, datasets, baselines, deciding metric, procedure, and threats to validity.",
    placeholder: "Any constraint on the experiments (compute, data)?",
    defaultQuestion: "Design experiments to test the open problems in this literature",
  },
  {
    flow: "novelty",
    title: "Check what is new here",
    icon: Compass,
    description:
      "Scores a claim against the passages this project has indexed and says whether they already cover it. Reports coverage in your corpus only — it will not claim anything is novel in the field.",
    placeholder: "Which claim or idea should be checked?",
    defaultQuestion: "Is this idea already covered by the indexed sources?",
  },
  {
    flow: "review",
    title: "Literature review",
    icon: Library,
    description:
      "The long chain: finds papers on the topic, indexes them, retrieves the passages back, contrasts them in a cited table, then reports what is new to this project.",
    placeholder: "Which topic should be reviewed?",
    defaultQuestion: "Review the recent literature on retrieval-augmented generation",
  },
  {
    flow: "patent",
    title: "Patent awareness",
    icon: ScrollText,
    description:
      "Locates where this project's concepts appear in patent text you pasted — down to the claim — and ranks each overlap by an explainable similarity score.",
    placeholder: "Which part of the work should be checked?",
    defaultQuestion: "Which concepts in this project overlap the stored patent text?",
  },
];

/** Tab: run a research workflow through the orchestrator and see its output. */
export function WorkflowPanel({ projectId, onTaskStarted, examples }: Props) {
  const [questions, setQuestions] = useState<Record<string, string>>({});
  const [activeFlow, setActiveFlow] = useState<string | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const track = useCallback((taskId: string) => {
    if (timer.current) clearInterval(timer.current);
    const tick = () =>
      api
        .getTask(taskId)
        .then((next) => {
          setTask(next);
          setError(null);
          if (next.status === "completed" || next.status === "failed") {
            if (timer.current) clearInterval(timer.current);
            setActiveFlow(null);
          }
        })
        .catch((err) => {
          // Keep polling after a transient read failure; stopping here left a
          // queued task with no result and no indication of what went wrong.
          setError(describeError(err, "Could not check workflow progress. Retrying…"));
        });
    tick();
    timer.current = setInterval(tick, 1500);
  }, []);

  const start = useCallback(
    async (spec: WorkflowSpec) => {
      const question = (questions[spec.flow] || spec.defaultQuestion).trim();
      setActiveFlow(spec.flow);
      setError(null);
      setTask(null);
      try {
        const started = await api.createTask(projectId, question, spec.flow);
        setTask(started);
        onTaskStarted?.(started.id);
        track(started.id);
      } catch (err) {
        setError(describeError(err, "Could not start the workflow"));
        setActiveFlow(null);
      }
    },
    [projectId, questions, onTaskStarted, track],
  );

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 py-2">
      <p className="text-sm text-muted-foreground">
        Each workflow runs through the same orchestrator as search and chat, emits its
        steps to the Tasks trace, and grounds its output in retrieved passages.
      </p>

      {error && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-start gap-3 p-4 text-sm">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <span>{error}</span>
          </CardContent>
        </Card>
      )}

      {WORKFLOWS.map((spec) => {
        const Icon = spec.icon;
        const running = activeFlow === spec.flow;
        const value = questions[spec.flow] ?? "";
        const tooShort = spec.multiline && value.trim().length < MIN_DESCRIPTION_CHARS;
        const onChange = (
          event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
        ) => setQuestions((prev) => ({ ...prev, [spec.flow]: event.target.value }));
        const example = examples?.[spec.flow];
        const useExample = example ? (
          <Button
            variant="outline"
            onClick={() => setQuestions((prev) => ({ ...prev, [spec.flow]: example }))}
            disabled={running}
            aria-label={`Use the example input for ${spec.title}`}
          >
            <Sparkles /> Use example
          </Button>
        ) : null;
        return (
          <Card key={spec.flow}>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Icon className="h-4 w-4 text-primary" /> {spec.title}
              </CardTitle>
              <CardDescription>{spec.description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {spec.flow === "patent" && (
                <>
                  <PatentDisclaimer />
                  <Button asChild variant="outline" size="sm">
                    <Link href={`/projects/${projectId}/patents`}>
                      Manage patents, metadata and exports <ArrowRight />
                    </Link>
                  </Button>
                </>
              )}
              {spec.multiline ? (
                <div className="space-y-2">
                  <Textarea
                    aria-label={spec.title}
                    aria-describedby={`${spec.flow}-hint`}
                    value={value}
                    onChange={onChange}
                    placeholder={spec.placeholder}
                    disabled={running}
                    rows={6}
                    maxLength={6000}
                  />
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <p id={`${spec.flow}-hint`} className="text-xs text-muted-foreground">
                      {tooShort
                        ? `${value.trim().length} / ${MIN_DESCRIPTION_CHARS} characters minimum`
                        : `${value.trim().length} characters`}
                    </p>
                    <div className="flex gap-2">
                      {useExample}
                      <Button onClick={() => start(spec)} disabled={running || tooShort}>
                        {running ? <Loader2 className="animate-spin" /> : <Play />}
                        Review project
                      </Button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input
                    aria-label={`${spec.title}: ${spec.placeholder}`}
                    value={value}
                    onChange={onChange}
                    placeholder={spec.placeholder}
                    disabled={running}
                  />
                  {useExample}
                  <Button onClick={() => start(spec)} disabled={running}>
                    {running ? <Loader2 className="animate-spin" /> : <Play />}
                    Run
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}

      {task && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Run progress</CardTitle>
            <CardDescription className="truncate">{task.request}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <PipelineTrace task={task} compact />

            {task.result?.answer && (
              <section aria-label="Final answer" className="space-y-1.5">
                <h4 className="text-sm font-medium">Final answer</h4>
                <p className="whitespace-pre-wrap rounded-lg border bg-muted/40 p-4 text-sm">
                  {task.result.answer}
                </p>
              </section>
            )}

            {task.status === "failed" && (
              <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
                {task.error ?? "The workflow failed."}
              </p>
            )}

            {task.result && <WorkflowSections result={task.result} />}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default WorkflowPanel;
