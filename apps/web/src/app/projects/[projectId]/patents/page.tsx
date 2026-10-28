"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  FileDown,
  Loader2,
  Pencil,
  Play,
  Plus,
  Printer,
  RefreshCw,
  ScrollText,
  Trash2,
} from "lucide-react";

import { PatentDetailView } from "@/components/patents/PatentDetailView";
import { PatentDisclaimer } from "@/components/patents/PatentDisclaimer";
import { PatentFindingsList } from "@/components/patents/PatentFindingsList";
import { PatentForm } from "@/components/patents/PatentForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { setActiveProjectId } from "@/lib/activeProject";
import {
  api,
  type PatentAwarenessResult,
  type PatentDetail,
  type PatentInput,
  type PatentRecord,
  type ProjectDetail,
} from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

type Mode = { kind: "detail" } | { kind: "add" } | { kind: "edit" };

const PATENT_FLOW_QUESTION = "Which concepts in this project overlap the stored patent text?";

/**
 * Patents: list, detail (metadata + segmented claims), computed findings,
 * exports and the printable view — for one project.
 *
 * The disclaimer is rendered unconditionally at the top, so it is present in
 * every state of the page: loading, error, empty and results.
 */
export default function PatentsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const router = useRouter();

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [patents, setPatents] = useState<PatentRecord[]>([]);
  const [allowed, setAllowed] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PatentDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>({ kind: "detail" });

  const [findings, setFindings] = useState<PatentAwarenessResult | null>(null);
  const [findingsLoading, setFindingsLoading] = useState(true);
  const [findingsError, setFindingsError] = useState<string | null>(null);

  const [toDelete, setToDelete] = useState<PatentRecord | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState<"run" | "markdown" | "csv" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadFindings = useCallback(async () => {
    setFindingsLoading(true);
    setFindingsError(null);
    try {
      setFindings(await api.patentFindings(projectId));
    } catch (err) {
      setFindingsError(describeError(err, "Could not compute the findings."));
    } finally {
      setFindingsLoading(false);
    }
  }, [projectId]);

  const loadPatents = useCallback(async () => {
    try {
      const [detailPayload, list] = await Promise.all([
        api.getProject(projectId),
        api.listPatents(projectId),
      ]);
      setProject(detailPayload);
      setPatents(list.patents);
      setLoadError(null);
      setSelectedId((current) =>
        current && list.patents.some((p) => p.id === current) ? current : (list.patents[0]?.id ?? null),
      );
    } catch (err) {
      setLoadError(describeError(err, "Could not load this project's patents."));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const refreshAll = useCallback(() => {
    void loadPatents();
    void loadFindings();
  }, [loadPatents, loadFindings]);

  useEffect(() => {
    setActiveProjectId(projectId);
    refreshAll();
    api
      .patentSources()
      .then((payload) => setAllowed(payload.sources.map((source) => source.domain)))
      .catch(() => setAllowed([]));
  }, [projectId, refreshAll]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailError(null);
    api
      .getPatent(projectId, selectedId)
      .then((payload) => !cancelled && setDetail(payload))
      .catch((err) => !cancelled && setDetailError(describeError(err, "Could not load this patent.")));
    return () => {
      cancelled = true;
    };
  }, [projectId, selectedId, patents]);

  async function create(input: PatentInput) {
    const saved = await api.addPatent(projectId, input);
    setSelectedId(saved.id);
    setMode({ kind: "detail" });
    refreshAll();
    return saved;
  }

  async function update(input: PatentInput) {
    if (!selectedId) throw new Error("No patent selected");
    const saved = await api.updatePatent(projectId, selectedId, input);
    setMode({ kind: "detail" });
    refreshAll();
    return saved;
  }

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await api.deletePatent(projectId, toDelete.id);
      setNotice(`Removed “${toDelete.title}”.`);
      setToDelete(null);
      if (selectedId === toDelete.id) setSelectedId(null);
      refreshAll();
    } catch (err) {
      setActionError(describeError(err, "Could not remove the patent."));
    } finally {
      setDeleting(false);
    }
  }

  async function runFlow() {
    setBusy("run");
    setActionError(null);
    try {
      await api.createTask(projectId, PATENT_FLOW_QUESTION, "patent");
      // Every run's live trace is on the Tasks page.
      router.push("/tasks");
    } catch (err) {
      setActionError(describeError(err, "Could not start the patent workflow."));
      setBusy(null);
    }
  }

  async function exportAs(format: "markdown" | "csv") {
    setBusy(format);
    setActionError(null);
    try {
      const filename = await api.exportPatentFindings(projectId, format);
      setNotice(`Downloaded ${filename}. The file carries the full disclaimer.`);
    } catch (err) {
      setActionError(describeError(err, "Could not export the findings."));
    } finally {
      setBusy(null);
    }
  }

  const selected = patents.find((p) => p.id === selectedId) ?? null;

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 p-4 sm:p-6 md:p-8">
      <header className="space-y-3">
        <Link
          href={`/projects/${projectId}`}
          className="focus-ring inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to workspace
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <ScrollText className="h-5 w-5 text-frozen" aria-hidden="true" /> Patents
            </h1>
            <p className="truncate text-sm text-muted-foreground">
              {project ? project.name : loading ? "Loading project…" : "—"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setMode({ kind: "add" })} disabled={!!loadError}>
              <Plus /> Add patent
            </Button>
            <Button variant="outline" onClick={runFlow} disabled={busy !== null || patents.length === 0}>
              {busy === "run" ? <Loader2 className="animate-spin" /> : <Play />} Run patent workflow
            </Button>
          </div>
        </div>
      </header>

      <PatentDisclaimer full />

      {notice && (
        <p className="rounded-md border bg-muted/40 p-2.5 text-xs" role="status">
          {notice}
        </p>
      )}
      {actionError && (
        <p role="alert" className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-2.5 text-sm">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
          {actionError}
        </p>
      )}

      {loadError ? (
        <section role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-5">
          <h2 className="font-semibold">Unable to load patents</h2>
          <p className="mt-1 text-sm text-muted-foreground">{loadError}</p>
          <Button className="mt-3" variant="outline" onClick={() => { setLoading(true); refreshAll(); }}>
            <RefreshCw /> Retry
          </Button>
        </section>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <Card className="min-w-0">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Supplied patents</CardTitle>
              <CardDescription>Text you pasted. Nothing here was downloaded.</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-2" role="status" aria-label="Loading patents">
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                </div>
              ) : patents.length === 0 ? (
                <div className="space-y-3 py-4 text-sm text-muted-foreground">
                  <p>No patents yet. Paste a patent’s abstract or claims to compare it with this project’s sources.</p>
                  <Button variant="outline" size="sm" onClick={() => setMode({ kind: "add" })}>
                    <Plus /> Add the first patent
                  </Button>
                </div>
              ) : (
                <ul className="space-y-2" aria-label="Patents">
                  {patents.map((patent) => (
                    <li key={patent.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedId(patent.id);
                          setMode({ kind: "detail" });
                        }}
                        aria-current={patent.id === selectedId && mode.kind !== "add" ? "true" : undefined}
                        className={`focus-ring w-full rounded-lg border p-3 text-left text-sm transition-colors hover:bg-accent/50 ${
                          patent.id === selectedId && mode.kind !== "add" ? "border-primary bg-accent/40" : ""
                        }`}
                      >
                        <span className="line-clamp-2 font-medium">{patent.title}</span>
                        <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                          {patent.number && <span>{patent.number}</span>}
                          <Badge variant="outline" className="text-[10px]">
                            {patent.segmented ? `${patent.claim_count ?? 0} claim(s)` : "not segmented"}
                          </Badge>
                          {patent.family_id && <span>family {patent.family_id}</span>}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card className="min-w-0">
            {mode.kind === "add" ? (
              <>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Add a patent</CardTitle>
                  <CardDescription>Paste the text and enter what you know; everything except the title is optional.</CardDescription>
                </CardHeader>
                <CardContent>
                  <PatentForm allowedDomains={allowed} onSubmit={create} onCancel={() => setMode({ kind: "detail" })} />
                </CardContent>
              </>
            ) : mode.kind === "edit" && selected ? (
              <>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Edit “{selected.title}”</CardTitle>
                </CardHeader>
                <CardContent>
                  <PatentForm
                    key={selected.id}
                    patent={selected}
                    allowedDomains={allowed}
                    onSubmit={update}
                    onCancel={() => setMode({ kind: "detail" })}
                  />
                </CardContent>
              </>
            ) : selected ? (
              <>
                <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 space-y-0 pb-3">
                  <div className="min-w-0">
                    <CardTitle className="text-base">{selected.title}</CardTitle>
                    <CardDescription>Added {new Date(selected.added_at).toLocaleDateString()}</CardDescription>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" onClick={() => setMode({ kind: "edit" })}>
                      <Pencil /> Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setToDelete(selected)}
                    >
                      <Trash2 /> Remove
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {detailError ? (
                    <p role="alert" className="text-sm text-destructive">{detailError}</p>
                  ) : detail && detail.patent.id === selected.id ? (
                    <PatentDetailView detail={detail} />
                  ) : (
                    <div className="space-y-2" role="status" aria-label="Loading patent">
                      <Skeleton className="h-24 w-full" />
                      <Skeleton className="h-40 w-full" />
                    </div>
                  )}
                </CardContent>
              </>
            ) : (
              <CardContent className="py-16 text-center text-sm text-muted-foreground">
                {loading ? "Loading…" : "Select a patent, or add one, to see its claims and metadata."}
              </CardContent>
            )}
          </Card>
        </div>
      )}

      <section aria-labelledby="findings-heading" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="findings-heading" className="text-lg font-semibold">Wording overlaps with this project</h2>
            <p className="text-sm text-muted-foreground">
              Computed from your patents and this project’s indexed passages. No model is involved.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => exportAs("markdown")} disabled={busy !== null}>
              {busy === "markdown" ? <Loader2 className="animate-spin" /> : <FileDown />} Export Markdown
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportAs("csv")} disabled={busy !== null}>
              {busy === "csv" ? <Loader2 className="animate-spin" /> : <FileDown />} Export CSV
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href={`/projects/${projectId}/patents/print`}>
                <Printer /> Printable view
              </Link>
            </Button>
          </div>
        </div>

        <Card>
          <CardContent className="p-4">
            {findingsLoading && !findings ? (
              <div className="space-y-2" role="status" aria-label="Computing findings">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
            ) : findingsError ? (
              <div role="alert" className="space-y-2 text-sm">
                <p>{findingsError}</p>
                <Button variant="outline" size="sm" onClick={() => void loadFindings()}>
                  <RefreshCw /> Retry
                </Button>
              </div>
            ) : findings ? (
              <PatentFindingsList result={findings} />
            ) : null}
          </CardContent>
        </Card>
      </section>

      <Dialog open={toDelete !== null} onOpenChange={(open) => !open && !deleting && setToDelete(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Remove this patent?</DialogTitle>
            <DialogDescription>
              “{toDelete?.title}” and its pasted text will be removed from this project. Its findings
              disappear from the overlap list and future exports.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setToDelete(null)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={deleting}>
              {deleting && <Loader2 className="animate-spin" />} Remove patent
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
