"use client";

import { useId, useState } from "react";
import { AlertCircle, Download, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

/** What the archive contains — mirrors `apps/api/app/export.py`. */
const CONTENTS: { file: string; what: string }[] = [
  { file: "project.json", what: "the project, its documents and discovered papers" },
  { file: "chunks.jsonl / .csv", what: "every indexed passage, with document, page and chunk index" },
  { file: "graph.json", what: "the knowledge graph" },
  { file: "tasks.jsonl", what: "every agent run with its events and results" },
  { file: "evaluation.json", what: "the latest evaluation report, if one was run" },
  { file: "patents.json", what: "patent text and metadata you supplied" },
  { file: "README.txt, manifest.json", what: "what is inside, its caveats, and a SHA-256 per file" },
];

/**
 * Download everything a project holds. Distinct from the patent-findings
 * export: this is the project's data, not a report.
 */
export function ProjectExportDialog({
  projectId,
  open,
  onOpenChange,
  returnFocusTo,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The control that opened the dialog. Radix only restores focus to its own
   *  trigger; opened from an ordinary button, focus fell back to <body>. */
  returnFocusTo?: React.RefObject<HTMLElement>;
}) {
  const uid = useId();
  const [format, setFormat] = useState<"zip" | "json">("zip");
  const [includeOriginals, setIncludeOriginals] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const filename = await api.exportProject(projectId, format, format === "zip" && includeOriginals);
      setDone(`Downloaded ${filename}.`);
    } catch (err) {
      setError(describeError(err, "Could not export this project."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent
        className="max-h-[90vh] overflow-y-auto sm:max-w-lg"
        onCloseAutoFocus={(event) => {
          if (returnFocusTo?.current) {
            event.preventDefault();
            returnFocusTo.current.focus();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>Export project data</DialogTitle>
          <DialogDescription>
            Everything this project holds, in open formats you can use without MAIROS.
          </DialogDescription>
        </DialogHeader>

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Format</legend>
          {(
            [
              ["zip", "ZIP archive", "Separate files, CSV included; can include the original PDFs."],
              ["json", "Single JSON file", "The same data in one document, without the PDFs."],
            ] as const
          ).map(([value, label, hint]) => (
            <label
              key={value}
              className="flex cursor-pointer items-start gap-2.5 rounded-md border p-2.5 text-sm has-[:checked]:border-primary has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring"
            >
              <input
                type="radio"
                name={`${uid}-format`}
                value={value}
                checked={format === value}
                onChange={() => setFormat(value)}
                className="mt-1 accent-[var(--primary)]"
              />
              <span>
                <span className="font-medium">{label}</span>
                <span className="block text-xs text-muted-foreground">{hint}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <label
          className={`flex items-start gap-2.5 text-sm ${format === "json" ? "opacity-60" : "cursor-pointer"}`}
        >
          <input
            type="checkbox"
            checked={format === "zip" && includeOriginals}
            disabled={format === "json"}
            onChange={(event) => setIncludeOriginals(event.target.checked)}
            aria-describedby={`${uid}-originals-hint`}
            className="mt-1 accent-[var(--primary)]"
          />
          <span>
            Include the original PDFs
            <span id={`${uid}-originals-hint`} className="block text-xs text-muted-foreground">
              {format === "json"
                ? "Only available in a ZIP."
                : "Off by default: they can be large, and they are the files you uploaded."}
            </span>
          </span>
        </label>

        <div className="rounded-md border bg-muted/30 p-3">
          <p className="mb-1.5 text-xs font-medium">Included</p>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {CONTENTS.map((item) => (
              <li key={item.file}>
                <span className="font-mono text-foreground">{item.file}</span> — {item.what}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Agent output in the export carries the same limits as in the app, and the README
            inside says so.
          </p>
        </div>

        {error && (
          <p role="alert" className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-2.5 text-sm">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
            {error}
          </p>
        )}
        {done && (
          <p role="status" className="rounded-md border bg-muted/40 p-2.5 text-sm">
            {done}
          </p>
        )}

        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            Close
          </Button>
          <Button onClick={() => void download()} disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : <Download />}
            {busy ? "Preparing…" : `Download ${format === "zip" ? "ZIP" : "JSON"}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ProjectExportDialog;
