"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Printer } from "lucide-react";

import { PatentDisclaimer } from "@/components/patents/PatentDisclaimer";
import { PatentFindingsList } from "@/components/patents/PatentFindingsList";
import { Button } from "@/components/ui/button";
import { api, type PatentAwarenessResult, type PatentRecord, type ProjectDetail } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";
import { PATENT_FULL_DISCLAIMER } from "@/lib/patentCopy";

/**
 * Printable findings. Self-contained on paper: the full disclaimer is printed
 * at the top and again at the end, the patents' metadata is listed, and every
 * citation is written out in full rather than behind a chip that cannot be
 * clicked on paper. The app chrome is hidden from print by `print:hidden`.
 */
export default function PrintablePatentFindings() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [patents, setPatents] = useState<PatentRecord[]>([]);
  const [findings, setFindings] = useState<PatentAwarenessResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Stamped when the findings arrive, on the client only: rendering
  // `new Date()` during the server pass as well can never match on hydration.
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getProject(projectId), api.listPatents(projectId), api.patentFindings(projectId)])
      .then(([projectDetail, list, result]) => {
        setProject(projectDetail);
        setPatents(list.patents);
        setFindings(result);
        setGeneratedAt(new Date().toLocaleString());
      })
      .catch((err) => setError(describeError(err, "Could not load the findings to print.")));
  }, [projectId]);

  return (
    <article className="mx-auto w-full max-w-4xl space-y-6 p-4 sm:p-8 print:max-w-none print:p-0 print:text-black">
      <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <Link
          href={`/projects/${projectId}/patents`}
          className="focus-ring inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to patents
        </Link>
        <Button onClick={() => window.print()} disabled={!findings}>
          <Printer /> Print
        </Button>
      </div>

      <header>
        <h1 className="text-2xl font-semibold">Patent wording overlaps</h1>
        <p className="text-sm text-muted-foreground print:text-black">
          {project?.name ?? "…"}
          {generatedAt ? ` · generated ${generatedAt} by MAIROS` : ""}
        </p>
      </header>

      <PatentDisclaimer full text={findings?.full_disclaimer} />

      {error ? (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          {error}
        </p>
      ) : !findings ? (
        <p role="status" className="text-sm text-muted-foreground">
          Preparing the printable view…
        </p>
      ) : (
        <>
          {patents.length > 0 && (
            <section aria-label="Patents checked" className="space-y-2">
              <h2 className="text-lg font-semibold">Patents checked</h2>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="border-b text-left print:border-black">
                    <th className="py-1 pr-2 font-medium">Title</th>
                    <th className="py-1 pr-2 font-medium">Publication no.</th>
                    <th className="py-1 pr-2 font-medium">Family</th>
                    <th className="py-1 pr-2 font-medium">Assignee</th>
                    <th className="py-1 font-medium">CPC / IPC</th>
                  </tr>
                </thead>
                <tbody>
                  {patents.map((patent) => (
                    <tr key={patent.id} className="border-b align-top print:border-black">
                      <td className="py-1 pr-2">{patent.title}</td>
                      <td className="py-1 pr-2">{patent.number || "—"}</td>
                      <td className="py-1 pr-2">{patent.family_id || "—"}</td>
                      <td className="py-1 pr-2">{patent.assignee || "—"}</td>
                      <td className="py-1">{[...patent.cpc_codes, ...patent.ipc_codes].join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <section aria-label="Findings" className="space-y-2">
            <h2 className="text-lg font-semibold">Findings</h2>
            <PatentFindingsList result={findings} printable />
          </section>
        </>
      )}

      <footer className="border-t pt-3 text-xs italic print:border-black">{PATENT_FULL_DISCLAIMER}</footer>
    </article>
  );
}
