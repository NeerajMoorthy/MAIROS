"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  Search,
  Sparkles,
  UploadCloud,
} from "lucide-react";

import { PipelineTrace } from "@/components/PipelineTrace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api, type DocumentSummary, type Paper, type Task } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

interface Props {
  projectId: string;
  documents: DocumentSummary[];
  onTaskStarted: (taskId: string) => void;
  onChanged: () => void;
}

/** Where a paper link goes, in words. The backend only sends allowlisted hosts. */
function linkLabel(url: string): string {
  if (url.includes("doi.org/")) return "View publication";
  if (url.includes("arxiv.org/")) return "View on arXiv";
  if (url.includes("semanticscholar.org/")) return "View on Semantic Scholar";
  if (url.includes("openalex.org/")) return "View on OpenAlex";
  return "View source";
}

/** Tab (a): the two entry points into the pipeline — topic search and PDF upload. */
export function SearchUpload({ projectId, documents, onTaskStarted, onChanged }: Props) {
  const [topic, setTopic] = useState("");
  const [searching, setSearching] = useState(false);
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [liveTask, setLiveTask] = useState<Task | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const uploading = uploadPercent !== null;

  const loadPapers = useCallback(() => {
    api
      .listPapers(projectId)
      .then(setPapers)
      .catch(() => setPapers([]));
  }, [projectId]);

  useEffect(() => {
    loadPapers();
  }, [loadPapers]);

  // Real progress, not a spinner standing in for it: poll the task this
  // panel just started until it settles, so "processing" reflects actual
  // backend events rather than a guess at how long ingestion takes.
  const trackTask = useCallback((taskId: string) => {
    if (pollTimer.current) clearInterval(pollTimer.current);
    const tick = () =>
      api
        .getTask(taskId)
        .then((task) => {
          setLiveTask(task);
          if (task.status === "completed" || task.status === "failed") {
            if (pollTimer.current) clearInterval(pollTimer.current);
          }
        })
        .catch(() => {
          if (pollTimer.current) clearInterval(pollTimer.current);
        });
    tick();
    pollTimer.current = setInterval(tick, 1500);
  }, []);

  useEffect(() => () => { if (pollTimer.current) clearInterval(pollTimer.current); }, []);

  async function handleSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!topic.trim()) return;

    setSearching(true);
    setError(null);
    setSuccess(null);
    try {
      // No `flow` — the Orchestrator's Router decides which agents to run.
      const task = await api.createTask(projectId, topic.trim());
      onTaskStarted(task.id);
      trackTask(task.id);
      setSuccess(`Search started for "${topic.trim()}" — follow it below.`);
      setTopic("");
      setTimeout(loadPapers, 2500);
    } catch (err) {
      setError(describeError(err, "Search failed"));
    } finally {
      setSearching(false);
    }
  }

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploadPercent(0);
    setError(null);
    setSuccess(null);
    setLiveTask(null);
    try {
      const result = await api.uploadDocumentWithProgress(projectId, file, setUploadPercent);
      onChanged();
      setSuccess(
        `Uploaded "${file.name}" — ${result.num_pages} pages, ${result.num_chunks} chunks indexed.`,
      );
      if (result.task_id) {
        onTaskStarted(result.task_id);
        trackTask(result.task_id);
      }
    } catch (err) {
      setError(describeError(err, "Upload failed"));
    } finally {
      setUploadPercent(null);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  const showGettingStarted = documents.length === 0 && papers.length === 0 && !liveTask;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 py-2">
      {showGettingStarted && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="flex items-start gap-3 p-4 text-sm">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <div>
              <p className="font-medium">This project is empty — start with one of the two actions below.</p>
              <p className="mt-1 text-muted-foreground">
                Search a topic to pull papers from arXiv, OpenAlex and Semantic Scholar, or upload a PDF to analyse a specific
                document. Either one kicks off the multi-agent pipeline automatically.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {error && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-start gap-3 p-4 text-sm">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <span>{error}</span>
          </CardContent>
        </Card>
      )}

      {success && (
        <Card className="border-success/40 bg-success/5">
          <CardContent className="flex items-start gap-3 p-4 text-sm">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            <span>{success}</span>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Search className="h-4 w-4 text-primary" /> Topic search
          </CardTitle>
          <CardDescription>
            Runs Literature → Indexer → Knowledge Graph → Citation → Synthesis.
            Searches arXiv, OpenAlex and Semantic Scholar with several queries,
            merges duplicates, then embeds the abstracts and adds them to the
            graph. The run reports which sources answered and what it kept.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSearch} className="flex flex-col gap-2 sm:flex-row">
            <Input
              aria-label="Topic to search the literature for"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="e.g. retrieval augmented generation for scientific QA"
              disabled={searching}
            />
            <Button type="submit" disabled={searching || !topic.trim()}>
              {searching ? <Loader2 className="animate-spin" /> : <Search />}
              Search
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <UploadCloud className="h-4 w-4 text-primary" /> Upload a PDF
          </CardTitle>
          <CardDescription>
            Extracts text with page numbers, embeds it, then runs Analysis →
            Knowledge Graph → Citation.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <label
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed py-10 transition-colors hover:bg-accent/40 ${
              uploading ? "pointer-events-none opacity-90" : ""
            }`}
          >
            {uploading ? (
              <>
                <div className="mb-3 h-1.5 w-48 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-200"
                    style={{ width: `${uploadPercent}%` }}
                  />
                </div>
                <span className="text-sm font-medium">
                  {uploadPercent! < 100
                    ? `Uploading… ${uploadPercent}%`
                    : "Extracting, chunking, and embedding…"}
                </span>
              </>
            ) : (
              <>
                <UploadCloud className="mb-3 h-7 w-7 text-muted-foreground" />
                <span className="text-sm font-medium">
                  Click to choose a PDF
                </span>
                <span className="mt-1 text-xs text-muted-foreground">
                  Text-based PDFs only — scanned images need OCR
                </span>
              </>
            )}
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </CardContent>
      </Card>

      {liveTask && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Pipeline progress</CardTitle>
            <CardDescription>Live status for this run — open Tasks for the full trace.</CardDescription>
          </CardHeader>
          <CardContent>
            <PipelineTrace task={liveTask} compact />
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              Uploaded documents
              <Badge variant="secondary" className="ml-2">
                {documents.length}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {documents.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                No documents yet — upload a PDF above to get started.
              </p>
            ) : (
              <ScrollArea className="h-56 pr-3">
                <ul className="space-y-2">
                  {documents.map((doc) => (
                    <li
                      key={doc.id}
                      className="flex items-start gap-2.5 rounded-md border p-2.5 text-sm"
                    >
                      <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                      <div className="min-w-0">
                        <p className="truncate font-medium">{doc.filename}</p>
                        <p className="text-xs text-muted-foreground">
                          {doc.num_pages} pages · {doc.num_chunks} chunks
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              Retrieved papers
              <Badge variant="secondary" className="ml-2">
                {papers.length}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {papers.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Run a topic search above to populate this list.
              </p>
            ) : (
              <ScrollArea className="h-56 pr-3">
                <ul className="space-y-2">
                  {papers.map((paper) => (
                    <li key={paper.id} className="rounded-md border p-2.5 text-sm">
                      <p className="line-clamp-2 font-medium">{paper.title}</p>
                      <p className="mt-1 truncate text-xs text-muted-foreground">
                        {paper.authors.slice(0, 3).join(", ")}
                        {paper.authors.length > 3 && " et al."}
                        {paper.year && ` · ${paper.year}`}
                        {paper.venue && ` · ${paper.venue}`}
                      </p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        {(paper.sources?.length ? paper.sources : [paper.source]).map((name) => (
                          <Badge key={name} variant="outline" className="text-[10px] font-normal">
                            {name}
                          </Badge>
                        ))}
                        {paper.url && (
                          <a
                            href={paper.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            {linkLabel(paper.url)} <ExternalLink className="h-3 w-3" aria-hidden="true" />
                          </a>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
