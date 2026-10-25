"use client";

import { useId, useState } from "react";
import { AlertCircle, Loader2, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PatentInput, PatentRecord } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

const splitList = (value: string) =>
  value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);

function initialValues(patent?: PatentRecord | null) {
  return {
    title: patent?.title ?? "",
    number: patent?.number ?? "",
    application_number: patent?.application_number ?? "",
    family_id: patent?.family_id ?? "",
    assignee: patent?.assignee ?? "",
    inventors: (patent?.inventors ?? []).join(", "),
    cpc_codes: (patent?.cpc_codes ?? []).join(", "),
    ipc_codes: (patent?.ipc_codes ?? []).join(", "),
    priority_date: patent?.priority_date ?? "",
    filing_date: patent?.filing_date ?? "",
    publication_date: patent?.publication_date ?? "",
    url: patent?.url ?? "",
    text: patent?.text ?? "",
  };
}

type Values = ReturnType<typeof initialValues>;

function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-xs font-medium">
        {label}
      </label>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="text-[11px] text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}

/**
 * Create or edit a patent: text plus bibliographic metadata, all typed by
 * hand. There is deliberately no "fetch from URL" button — MAIROS never
 * retrieves a patent document; the link is stored for a person to open.
 */
export function PatentForm({
  patent,
  allowedDomains = [],
  onSubmit,
  onCancel,
}: {
  patent?: PatentRecord | null;
  allowedDomains?: string[];
  onSubmit: (input: PatentInput) => Promise<PatentRecord>;
  onCancel?: () => void;
}) {
  const uid = useId();
  const [values, setValues] = useState<Values>(() => initialValues(patent));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  const set = (key: keyof Values) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setValues((prev) => ({ ...prev, [key]: event.target.value }));
  const id = (key: string) => `${uid}-${key}`;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!values.title.trim()) return;
    setSaving(true);
    setError(null);
    setWarnings([]);
    try {
      const saved = await onSubmit({
        title: values.title.trim(),
        number: values.number.trim(),
        application_number: values.application_number.trim(),
        family_id: values.family_id.trim(),
        assignee: values.assignee.trim(),
        inventors: splitList(values.inventors),
        cpc_codes: splitList(values.cpc_codes),
        ipc_codes: splitList(values.ipc_codes),
        priority_date: values.priority_date,
        filing_date: values.filing_date,
        publication_date: values.publication_date,
        url: values.url.trim(),
        text: values.text.trim(),
      });
      setWarnings(saved.warnings ?? []);
      if (!patent) setValues(initialValues(null));
    } catch (err) {
      setError(describeError(err, "Could not save the patent"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" aria-label={patent ? "Edit patent" : "Add a patent"}>
      {error && (
        <p role="alert" className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-2.5 text-xs">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden="true" />
          {error}
        </p>
      )}
      {warnings.length > 0 && (
        <ul role="status" className="space-y-1 rounded-md border border-warning/50 bg-warning/10 p-2.5 text-xs">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}

      <Field id={id("title")} label="Title (required)">
        <Input id={id("title")} value={values.title} onChange={set("title")} required disabled={saving} />
      </Field>

      <fieldset className="space-y-3 rounded-lg border p-3">
        <legend className="px-1 text-xs font-medium text-muted-foreground">Numbers and family</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field id={id("number")} label="Publication number" hint="e.g. US1234567B2">
            <Input id={id("number")} value={values.number} onChange={set("number")} disabled={saving} aria-describedby={`${id("number")}-hint`} />
          </Field>
          <Field id={id("application")} label="Application number">
            <Input id={id("application")} value={values.application_number} onChange={set("application_number")} disabled={saving} />
          </Field>
          <Field id={id("family")} label="Family id">
            <Input id={id("family")} value={values.family_id} onChange={set("family_id")} disabled={saving} />
          </Field>
        </div>
      </fieldset>

      <fieldset className="space-y-3 rounded-lg border p-3">
        <legend className="px-1 text-xs font-medium text-muted-foreground">Parties and classification</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field id={id("assignee")} label="Assignee">
            <Input id={id("assignee")} value={values.assignee} onChange={set("assignee")} disabled={saving} />
          </Field>
          <Field id={id("inventors")} label="Inventors" hint="Separate names with commas">
            <Input id={id("inventors")} value={values.inventors} onChange={set("inventors")} disabled={saving} aria-describedby={`${id("inventors")}-hint`} />
          </Field>
          <Field id={id("cpc")} label="CPC codes" hint="e.g. G06F 16/3347, G06N 3/08">
            <Input id={id("cpc")} value={values.cpc_codes} onChange={set("cpc_codes")} disabled={saving} aria-describedby={`${id("cpc")}-hint`} />
          </Field>
          <Field id={id("ipc")} label="IPC codes" hint="e.g. G06F 16/33">
            <Input id={id("ipc")} value={values.ipc_codes} onChange={set("ipc_codes")} disabled={saving} aria-describedby={`${id("ipc")}-hint`} />
          </Field>
        </div>
      </fieldset>

      <fieldset className="space-y-3 rounded-lg border p-3">
        <legend className="px-1 text-xs font-medium text-muted-foreground">
          Dates (must run priority → filing → publication)
        </legend>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field id={id("priority")} label="Priority date">
            <Input id={id("priority")} type="date" value={values.priority_date} onChange={set("priority_date")} disabled={saving} />
          </Field>
          <Field id={id("filing")} label="Filing date">
            <Input id={id("filing")} type="date" value={values.filing_date} onChange={set("filing_date")} disabled={saving} />
          </Field>
          <Field id={id("publication")} label="Publication date">
            <Input id={id("publication")} type="date" value={values.publication_date} onChange={set("publication_date")} disabled={saving} />
          </Field>
        </div>
      </fieldset>

      <Field
        id={id("url")}
        label="Public registry link (optional)"
        hint={
          allowedDomains.length
            ? `Stored for you to open — never fetched. Accepted: ${allowedDomains.join(", ")}`
            : "Stored for you to open — MAIROS never fetches it."
        }
      >
        <Input id={id("url")} type="url" value={values.url} onChange={set("url")} disabled={saving} aria-describedby={`${id("url")}-hint`} />
      </Field>

      <Field
        id={id("text")}
        label="Patent text"
        hint="Paste the abstract, description and/or claims. Headings such as “Abstract” and “Claims” and numbered claims are recognised."
      >
        <textarea
          id={id("text")}
          value={values.text}
          onChange={set("text")}
          disabled={saving}
          rows={8}
          aria-describedby={`${id("text")}-hint`}
          className="focus-ring w-full rounded-md border border-input bg-background p-2.5 font-mono text-xs leading-relaxed"
        />
      </Field>

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={saving || !values.title.trim()}>
          {saving ? <Loader2 className="animate-spin" /> : <Save />}
          {patent ? "Save changes" : "Add patent"}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

export default PatentForm;
