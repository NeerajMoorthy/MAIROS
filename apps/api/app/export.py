"""Project-wide data export: everything one project holds, in open formats.

Distinct from the patent-findings export (``services/patents/export.py``),
which is a report. This is the project's *data*, so that a researcher can take
it elsewhere — another tool, an archive, a reviewer — without MAIROS.

A ZIP contains:

    README.txt        what this is, counts, and the caveats generated content carries
    manifest.json     every file with its size and SHA-256
    project.json      the project, its documents and the papers it discovered
    chunks.jsonl      every indexed chunk, with document, page and chunk index
    chunks.csv        the same, for a spreadsheet
    graph.json        the knowledge graph, in the shape the UI reads
    tasks.jsonl       every agent run, with its events and result
    evaluation.json   the latest evaluation report, if one has been run
    patents.json      patent text and metadata the user supplied, with the disclaimer
    originals/        the uploaded PDFs — only when asked for

Three rules shape it:

* **Provenance survives.** Every chunk keeps ``document_name``, ``page`` and
  ``chunk_index``; a citation in an exported task result can still be followed
  to its passage.
* **Nothing is silently truncated.** The vector store is read with no row limit
  and counts in the README come from what was actually written.
* **Generated content keeps its caveats.** The README states, in the file
  itself, what the agents' output is and is not — the same limits the app
  shows next to it.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.dependencies import get_chroma_store
from app.store import metadata_store
from services.knowledge_graph.networkx_store import kg_store
from services.patents.sources import FULL_DISCLAIMER

EXPORT_FORMAT_VERSION = 1
CHUNK_CSV_COLUMNS = ("chunk_id", "document_id", "document_name", "source", "page", "chunk_index", "text")

# Kept in memory up to this size, then spilled to a temporary file, so a
# project with large originals does not hold them all in RAM.
_SPOOL_BYTES = 32 * 1024 * 1024

GENERATED_CONTENT_NOTE = (
    "Answers, comparisons, research gaps, hypotheses, experiment designs and "
    "novelty notes in tasks.jsonl were produced by MAIROS's agents. Each one is "
    "grounded only in the passages cited with it; anything the agents could not "
    "cite was dropped before it was stored, and the counts of what was dropped are "
    "kept alongside. Novelty results describe coverage in this project's sources "
    "only — 'field_novelty' is always 'not_assessed', and nothing here is a claim "
    "that an idea is new in the field."
)

EVALUATION_NOTE = (
    "Retrieval metrics in evaluation.json use a documented keyword relevance proxy, "
    "not human relevance labels. Any answer-quality scores in it are model-judged, "
    "not computed."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "project"


def _safe_filename(name: str) -> str:
    """A filename safe inside a ZIP: no directories, no control characters."""
    base = Path(str(name)).name
    cleaned = re.sub(r"[^\w.\- ()]+", "_", base).strip(" .")
    return cleaned or "document.pdf"


def _page(value) -> int | None:
    """Chunks with no known page are stored with -1; export that as null."""
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return page if page >= 0 else None


# ---------------------------------------------------------------------------
# Collecting
# ---------------------------------------------------------------------------
def collect(project_id: str) -> dict:
    """Everything the project holds, as plain JSON-ready data."""
    project = metadata_store.get_project(project_id)
    if project is None:
        raise KeyError(project_id)

    raw_chunks = get_chroma_store().all_chunks(project_id=project_id, limit=None)
    chunks = sorted(
        (
            {
                "chunk_id": chunk.get("chunk_id", ""),
                "document_id": chunk.get("document_id", ""),
                "document_name": chunk.get("document_name", ""),
                "source": chunk.get("source", ""),
                "page": _page(chunk.get("page")),
                "chunk_index": chunk.get("chunk_index"),
                "text": chunk.get("text", ""),
            }
            for chunk in raw_chunks
        ),
        key=lambda c: (c["document_name"], c["chunk_index"] if c["chunk_index"] is not None else 0, c["chunk_id"]),
    )

    evaluation = metadata_store.get_evaluation(project_id)
    return {
        "project": project.model_dump(mode="json"),
        "documents": [d.model_dump(mode="json") for d in metadata_store.list_documents(project_id)],
        "papers": [p.model_dump(mode="json") for p in metadata_store.list_papers(project_id)],
        "chunks": chunks,
        "graph": kg_store.to_json(project_id),
        # Oldest first: a history reads forwards.
        "tasks": [
            t.model_dump(mode="json")
            for t in reversed(metadata_store.list_tasks(project_id, limit=1_000_000))
        ],
        "evaluation": evaluation.model_dump(mode="json") if evaluation else None,
        "patents": [p.model_dump(mode="json") for p in metadata_store.list_patents(project_id)],
    }


def _originals(project_id: str, documents: list[dict]) -> list[tuple[str, Path]]:
    """``(name_in_zip, path_on_disk)`` for every uploaded original.

    Documents name their file through ``metadata.stored_file``. Files uploaded
    before that was recorded cannot be matched to a document, so they are
    included under ``originals/unmatched/`` rather than left out.
    """
    root = (Path(settings.upload_dir) / project_id).resolve()
    if not root.is_dir():
        return []

    on_disk = {path.name: path for path in root.iterdir() if path.is_file()}
    used_names: set[str] = set()
    out: list[tuple[str, Path]] = []

    def unique(name: str) -> str:
        stem, suffix = Path(name).stem, Path(name).suffix
        candidate, n = name, 2
        while candidate.lower() in used_names:
            candidate = f"{stem} ({n}){suffix}"
            n += 1
        used_names.add(candidate.lower())
        return candidate

    for document in documents:
        stored = str((document.get("metadata") or {}).get("stored_file", ""))
        path = on_disk.pop(stored, None) if stored else None
        # Only ever a direct child of this project's upload directory.
        if path is not None and path.resolve().parent == root:
            out.append((f"originals/{unique(_safe_filename(document.get('filename') or stored))}", path))

    for name, path in sorted(on_disk.items()):
        out.append((f"originals/unmatched/{_safe_filename(name)}", path))
    return out


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def _jsonl(rows: list[dict]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")


def _chunks_csv(chunks: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CHUNK_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for chunk in chunks:
        writer.writerow({key: "" if chunk.get(key) is None else chunk.get(key) for key in CHUNK_CSV_COLUMNS})
    # BOM so spreadsheet tools read the text as UTF-8.
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _readme(data: dict, generated: datetime, originals: int | None) -> str:
    project = data["project"]
    documents = data["documents"]
    evaluation = data["evaluation"]
    graph_stats = data["graph"].get("stats", {})

    lines = [
        "MAIROS project export",
        "=====================",
        "",
        f"Project:        {project['name']} ({project['id']})",
        f"Generated:      {generated.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Format version: {EXPORT_FORMAT_VERSION}",
        "",
        "Contents",
        "--------",
        "project.json     the project, its documents and the papers it discovered",
        f"chunks.jsonl     {len(data['chunks'])} indexed chunk(s) from {len(documents)} uploaded "
        "document(s) and any fetched abstracts; each has document_name, page and chunk_index",
        "chunks.csv       the same chunks as a spreadsheet",
        f"graph.json       knowledge graph: {graph_stats.get('nodes', 0)} node(s), {graph_stats.get('edges', 0)} edge(s)",
        f"tasks.jsonl      {len(data['tasks'])} agent run(s), oldest first, with events and results",
        (
            f"evaluation.json  latest evaluation report ({evaluation['created_at']})"
            if evaluation
            else "evaluation.json  not included: no evaluation has been run for this project"
        ),
        f"patents.json     {len(data['patents'])} patent record(s) supplied by the user",
        (
            f"originals/       {originals} uploaded PDF(s)"
            if originals is not None
            else "originals/       not included (export without originals)"
        ),
        "manifest.json    size and SHA-256 of every file above",
        "",
        "About generated content",
        "-----------------------",
        GENERATED_CONTENT_NOTE,
        "",
        EVALUATION_NOTE,
        "",
        "About patent records",
        "--------------------",
        FULL_DISCLAIMER,
        "",
    ]
    return "\n".join(lines)


def build_zip(project_id: str, include_originals: bool = False):
    """Write the ZIP to a spooled temporary file.

    Returns ``(file, size, filename)``. The file is positioned at the start;
    the caller streams it and closes it.
    """
    data = collect(project_id)
    generated = _now()
    originals = _originals(project_id, data["documents"]) if include_originals else []

    project_json = {
        "format_version": EXPORT_FORMAT_VERSION,
        "generated_at": generated.isoformat(),
        "project": data["project"],
        "documents": data["documents"],
        "papers": data["papers"],
    }
    patents_json = {"disclaimer": FULL_DISCLAIMER, "patents": data["patents"]}

    members: list[tuple[str, bytes]] = [
        ("project.json", json.dumps(project_json, indent=2, ensure_ascii=False).encode("utf-8")),
        ("chunks.jsonl", _jsonl(data["chunks"])),
        ("chunks.csv", _chunks_csv(data["chunks"])),
        ("graph.json", json.dumps(data["graph"], indent=2, ensure_ascii=False).encode("utf-8")),
        ("tasks.jsonl", _jsonl(data["tasks"])),
        ("patents.json", json.dumps(patents_json, indent=2, ensure_ascii=False).encode("utf-8")),
    ]
    if data["evaluation"]:
        members.append(("evaluation.json", json.dumps(data["evaluation"], indent=2, ensure_ascii=False).encode("utf-8")))
    members.insert(
        0,
        ("README.txt", _readme(data, generated, len(originals) if include_originals else None).encode("utf-8")),
    )

    manifest: list[dict] = []
    spool = tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES)
    with zipfile.ZipFile(spool, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members:
            archive.writestr(name, payload)
            manifest.append({"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})

        for name, path in originals:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            # PDFs are already compressed; deflating them again costs time for nothing.
            archive.write(path, arcname=name, compress_type=zipfile.ZIP_STORED)
            manifest.append({"path": name, "bytes": path.stat().st_size, "sha256": digest.hexdigest()})

        archive.writestr(
            "manifest.json",
            json.dumps(
                {"format_version": EXPORT_FORMAT_VERSION, "generated_at": generated.isoformat(), "files": manifest},
                indent=2,
            ),
        )

    size = spool.tell()
    spool.seek(0)
    filename = f"{_slug(data['project']['name'])}-export-{generated.strftime('%Y%m%d')}.zip"
    return spool, size, filename


def build_json(project_id: str) -> tuple[bytes, str]:
    """The same data as one JSON document (no originals)."""
    data = collect(project_id)
    generated = _now()
    payload = {
        "format_version": EXPORT_FORMAT_VERSION,
        "generated_at": generated.isoformat(),
        "notes": {
            "generated_content": GENERATED_CONTENT_NOTE,
            "evaluation": EVALUATION_NOTE,
            "patents": FULL_DISCLAIMER,
        },
        **data,
    }
    filename = f"{_slug(data['project']['name'])}-export-{generated.strftime('%Y%m%d')}.json"
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"), filename


__all__ = ["CHUNK_CSV_COLUMNS", "EXPORT_FORMAT_VERSION", "build_json", "build_zip", "collect"]
