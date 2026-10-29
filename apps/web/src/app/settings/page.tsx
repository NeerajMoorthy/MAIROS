"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  Download,
  FileText,
  Loader2,
  RotateCcw,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { clearActiveProjectId, setActiveProjectId } from "@/lib/activeProject";
import {
  api,
  type ExampleGuideStep,
  type ExampleWorkspaceInfo,
  type ExampleWorkspaceLoaded,
  type Project,
} from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

/** Where a guide step happens, as a link into the example project. */
function stepHref(projectId: string, step: ExampleGuideStep): string {
  if (step.where === "patents") return `/projects/${projectId}/patents`;
  if (step.where === "search") return `/projects/${projectId}`;
  return `/projects/${projectId}?tab=${step.where}`;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      size="sm"
      aria-label={`Copy the example input for ${label}`}
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(
          () => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          },
          () => {},
        );
      }}
    >
      {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
    </Button>
  );
}

/** Settings: load the example workspace, or clear every project. */
export default function SettingsPage() {
  const [info, setInfo] = useState<ExampleWorkspaceInfo | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState<ExampleWorkspaceLoaded | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const clearButton = useRef<HTMLButtonElement>(null);

  const refresh = useCallback(() => {
    api.listProjects().then(setProjects, () => setProjects(null));
  }, []);

  useEffect(() => {
    api.exampleWorkspace().then(setInfo, (err) =>
      setError(describeError(err, "Could not read the example workspace.")),
    );
    refresh();
  }, [refresh]);

  // The example already in the workspace, so the guide links work without reloading it.
  const exampleId =
    loaded?.project_id ?? projects?.find((p) => info && p.name === info.name)?.id ?? null;

  async function loadExample() {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await api.loadExampleWorkspace();
      setLoaded(result);
      setActiveProjectId(result.project_id);
      const chunks = result.documents.reduce((sum, d) => sum + d.num_chunks, 0);
      setMessage(
        `Loaded "${result.name}": ${result.documents.length} papers (${chunks} passages) and a patent.` +
          (result.replaced ? " The previous example project was replaced." : "") +
          " Each paper's analysis run continues in the background.",
      );
      refresh();
    } catch (err) {
      setError(describeError(err, "Could not load the example data."));
    } finally {
      setLoading(false);
    }
  }

  async function clearWorkspace() {
    setClearing(true);
    setError(null);
    setMessage(null);
    try {
      const { deleted } = await api.clearWorkspace();
      clearActiveProjectId();
      setLoaded(null);
      setMessage(
        deleted === 0
          ? "The workspace was already empty."
          : `Deleted ${deleted} project${deleted === 1 ? "" : "s"} and everything in them.`,
      );
      setConfirmOpen(false);
      refresh();
    } catch (err) {
      setError(describeError(err, "Could not clear the workspace."));
      setConfirmOpen(false);
    } finally {
      setClearing(false);
    }
  }

  async function downloadFile(name: string) {
    setError(null);
    try {
      await api.downloadSampleFile(name);
    } catch (err) {
      setError(describeError(err, `Could not download ${name}.`));
    }
  }

  const projectCount = projects?.length ?? null;

  return (
    <div className="h-[calc(100vh-3.5rem)] overflow-auto">
      <div className="border-b px-4 py-4 sm:px-6">
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">Example data and the workspace.</p>
      </div>

      <div className="mx-auto w-full max-w-4xl space-y-6 px-4 py-6 sm:px-6">
        {error && (
          <div role="alert" className="flex items-start gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <span>{error}</span>
          </div>
        )}
        {message && (
          <div role="status" className="flex items-start gap-3 rounded-md border border-primary/30 bg-primary/10 p-3 text-sm">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <span>{message}</span>
          </div>
        )}

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Example workspace</CardTitle>
            <CardDescription>
              Load a sample project to walk through MAIROS: three fictional papers on railway
              crack detection, already indexed, and a fictional patent. Loading it again replaces
              the previous example; your own projects are not touched.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <Button onClick={() => void loadExample()} disabled={loading || clearing}>
              {loading ? <Loader2 className="animate-spin" /> : <Sparkles />}
              {loading ? "Loading example data…" : "Load example data"}
            </Button>
            <Button
              ref={clearButton}
              variant="ghost"
              onClick={() => setConfirmOpen(true)}
              disabled={loading || clearing}
            >
              <RotateCcw /> Clear workspace
            </Button>
            {exampleId && (
              <Button asChild variant="outline">
                <Link href={`/projects/${exampleId}`}>
                  Open the example project <ArrowRight />
                </Link>
              </Button>
            )}
          </CardContent>
        </Card>

        {info && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Try every feature</CardTitle>
              <CardDescription>
                {exampleId
                  ? "Each step opens the right place in the example project. Copy the input, paste it there and run it."
                  : "Load the example data first; then each step links to the right place in it."}{" "}
                In the example project, workflow cards and Topic search also have a{" "}
                <span className="font-medium">Use example</span> button. Wait about a minute
                between runs on the free model tier.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ol className="space-y-3">
                {info.guide.map((step, index) => (
                  <li key={step.feature} className="rounded-lg border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-medium">
                        {index + 1}. {step.feature}
                      </p>
                      <div className="flex gap-1">
                        {step.input && <CopyButton text={step.input} label={step.feature} />}
                        {exampleId && (
                          <Button asChild variant="outline" size="sm">
                            <Link href={stepHref(exampleId, step)}>
                              Open <ArrowRight />
                            </Link>
                          </Button>
                        )}
                      </div>
                    </div>
                    {step.input && (
                      <p className="mt-2 line-clamp-3 whitespace-pre-wrap rounded-md bg-muted/40 p-2 font-mono text-xs">
                        {step.input}
                      </p>
                    )}
                    <p className="mt-2 text-xs text-muted-foreground">
                      <span className="font-medium text-foreground/80">Expect: </span>
                      {step.expect}
                    </p>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        )}

        {info && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Sample files</CardTitle>
              <CardDescription>
                Download these to try uploads yourself, including two files that must be refused.
                All of them are fictional and made for testing.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="divide-y">
                {info.files.map((file) => (
                  <li key={file.name} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <div className="min-w-0">
                      <p className="flex items-center gap-2 text-sm font-medium">
                        <FileText className="h-4 w-4 shrink-0 text-primary" /> {file.name}
                      </p>
                      <p className="text-xs text-muted-foreground">{file.description}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Download ${file.name}`}
                      onClick={() => void downloadFile(file.name)}
                    >
                      <Download /> Download
                    </Button>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>

      <Dialog open={confirmOpen} onOpenChange={(next) => !clearing && setConfirmOpen(next)}>
        <DialogContent
          className="sm:max-w-md"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            clearButton.current?.focus();
          }}
        >
          <DialogHeader>
            <DialogTitle>Clear the workspace?</DialogTitle>
            <DialogDescription>
              {projectCount === null
                ? "This deletes every project"
                : `This deletes ${projectCount === 1 ? "your 1 project" : `all ${projectCount} projects`}`}
              , with their uploaded files, indexed passages, knowledge graphs, task history,
              evaluations and patents. It cannot be undone. Export anything you want to keep first.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={clearing}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void clearWorkspace()} disabled={clearing}>
              {clearing ? <Loader2 className="animate-spin" /> : <RotateCcw />}
              Delete everything
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
