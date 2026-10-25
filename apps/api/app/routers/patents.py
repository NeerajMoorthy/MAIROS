"""Patents router — manual entry, segmented detail, computed findings, export.

MAIROS stores what the user pastes and, optionally, a link to a public
registry it validates but never visits. See ``services/patents/sources.py`` for
why there is no fetch path here at all.

Every response that can carry a finding also carries the disclaimer, and every
error message is worded so it cannot be read as a legal conclusion — the audit
in ``tests/test_patents.py`` scans this router's output for that.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.store import metadata_store
from schemas import Patent
from services.patents.export import findings_to_csv, findings_to_markdown
from services.patents.findings import compute_findings, project_concepts, slugify
from services.patents.metadata import (
    PatentMetadataError,
    check_date_order,
    clean_names,
    normalise_codes,
    number_warnings,
)
from services.patents.segmentation import segment_patent
from services.patents.sources import (
    DISCLAIMER,
    FULL_DISCLAIMER,
    PatentSourceError,
    describe_sources,
    validate_public_url,
)

router = APIRouter(tags=["patents"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class PatentMetadataFields(BaseModel):
    """Bibliographic metadata, all optional and all typed in by hand.

    Dates arrive as strings and are parsed here rather than by Pydantic, so a
    mistyped date gets a message that says which field and which format,
    instead of a generic validation dump.
    """

    application_number: str = ""
    family_id: str = ""
    cpc_codes: list[str] = Field(default_factory=list)
    ipc_codes: list[str] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    priority_date: str = ""
    filing_date: str = ""
    publication_date: str = ""


class CreatePatentRequest(PatentMetadataFields):
    """A patent the user entered by hand."""

    title: str = Field(..., min_length=1, description="Patent title")
    text: str = Field(
        "",
        description="Abstract, claims or full text, pasted by the user. MAIROS never fetches it.",
    )
    number: str = Field("", description="Publication number")
    url: str = Field("", description="Optional link to a public patent registry")
    assignee: str = Field("", description="Assignee or applicant, if known")


class UpdatePatentRequest(BaseModel):
    """Fields to change; anything omitted is left as it was."""

    title: str | None = Field(None, min_length=1)
    text: str | None = None
    number: str | None = None
    url: str | None = None
    assignee: str | None = None
    application_number: str | None = None
    family_id: str | None = None
    cpc_codes: list[str] | None = None
    ipc_codes: list[str] | None = None
    inventors: list[str] | None = None
    priority_date: str | None = None
    filing_date: str | None = None
    publication_date: str | None = None


class PatentResponse(Patent):
    """A stored patent plus what segmentation found and any input warnings."""

    segmented: bool = False
    claim_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    # Every patent response carries it, so no client can render a patent
    # record without the wording that governs it.
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_project(project_id: str):
    project = metadata_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_patent(project_id: str, patent_id: str) -> Patent:
    patent = metadata_store.get_patent(patent_id)
    if patent is None or patent.project_id != project_id:
        raise HTTPException(status_code=404, detail="Patent not found")
    return patent


def _parse_date(label: str, value: str | None) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"The {label} '{value}' is not a calendar date in YYYY-MM-DD form.",
        ) from None


def _validated_metadata(fields: dict) -> tuple[dict, list[str]]:
    """Normalise and check metadata; return ``(clean_fields, warnings)``.

    Only keys present in *fields* are returned, so the same function serves a
    full create and a partial update.
    """
    clean: dict = {}
    try:
        for key, scheme in (("cpc_codes", "CPC"), ("ipc_codes", "IPC")):
            if key in fields and fields[key] is not None:
                clean[key] = normalise_codes(fields[key], scheme)
    except PatentMetadataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if fields.get("inventors") is not None and "inventors" in fields:
        clean["inventors"] = clean_names(fields["inventors"])

    for key in ("application_number", "family_id", "number", "assignee", "title"):
        if key in fields and fields[key] is not None:
            clean[key] = " ".join(str(fields[key]).split())

    for key, label in (
        ("priority_date", "priority date"),
        ("filing_date", "filing date"),
        ("publication_date", "publication date"),
    ):
        if key in fields and fields[key] is not None:
            clean[key] = _parse_date(label, fields[key])

    warnings = number_warnings(clean.get("number", ""), clean.get("application_number", ""))
    return clean, warnings


def _check_dates(record: dict) -> None:
    try:
        check_date_order(
            record.get("priority_date"), record.get("filing_date"), record.get("publication_date")
        )
    except PatentMetadataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _respond(patent: Patent, warnings: list[str] | None = None) -> PatentResponse:
    segmented = segment_patent(patent.text or "")
    return PatentResponse(
        **patent.model_dump(),
        segmented=segmented.segmented,
        claim_count=len(segmented.claims),
        warnings=warnings or [],
    )


def _project_findings(project_id: str) -> dict:
    """Findings for the project's current patents — computed, never generated."""
    from app.dependencies import get_chroma_store

    try:
        corpus = get_chroma_store().all_chunks(project_id=project_id)
    except Exception:
        corpus = []
    patents = list(reversed(metadata_store.list_patents(project_id)))  # oldest first
    concepts = project_concepts(project_id, corpus)
    return compute_findings(patents, concepts, corpus)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/patents/sources")
async def patent_sources() -> dict:
    """Which public registries may be linked, and the standing disclaimer."""
    return describe_sources()


@router.post("/projects/{project_id}/patents", response_model=PatentResponse, status_code=201)
async def add_patent(project_id: str, request: CreatePatentRequest) -> PatentResponse:
    """Store a patent reference, with any metadata, for later awareness checks."""
    _require_project(project_id)

    try:
        url, source = validate_public_url(request.url)
    except PatentSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not request.text.strip() and not url:
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide the patent text to compare, a public registry link, or both. "
                "MAIROS does not retrieve patent documents itself."
            ),
        )

    fields, warnings = _validated_metadata(request.model_dump())
    _check_dates(fields)

    patent = metadata_store.add_patent(
        project_id=project_id,
        text=request.text.strip(),
        url=url,
        source=source,
        **fields,
    )
    return _respond(patent, warnings)


@router.get("/projects/{project_id}/patents")
async def list_patents(project_id: str) -> dict:
    """Patents stored for this project, with the disclaimer that governs them."""
    _require_project(project_id)
    return {
        "disclaimer": DISCLAIMER,
        "full_disclaimer": FULL_DISCLAIMER,
        "patents": [
            _respond(p).model_dump(mode="json") for p in metadata_store.list_patents(project_id)
        ],
    }


# Declared before /patents/{patent_id}, or "findings" would be read as an id.
@router.get("/projects/{project_id}/patents/findings")
async def patent_findings(project_id: str) -> dict:
    """Computed overlaps between this project's concepts and its stored patents."""
    _require_project(project_id)
    return _project_findings(project_id)


@router.get("/projects/{project_id}/patents/findings/export")
async def export_patent_findings(
    project_id: str,
    format: str = Query("markdown", pattern="^(markdown|md|csv)$"),
) -> Response:
    """Download findings as Markdown or CSV. The full disclaimer is in the body."""
    project = _require_project(project_id)
    result = _project_findings(project_id)
    stem = f"{slugify(project.name)}-patent-findings"

    if format == "csv":
        # A UTF-8 BOM so spreadsheet tools read the dashes and quotes correctly.
        body = "﻿" + findings_to_csv(result)
        media_type, filename = "text/csv; charset=utf-8", f"{stem}.csv"
    else:
        body = findings_to_markdown(result, project.name)
        media_type, filename = "text/markdown; charset=utf-8", f"{stem}.md"

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/projects/{project_id}/patents/{patent_id}")
async def get_patent(project_id: str, patent_id: str) -> dict:
    """One patent with its segmented abstract, description and claims."""
    _require_project(project_id)
    patent = _require_patent(project_id, patent_id)
    return {
        "disclaimer": DISCLAIMER,
        "patent": _respond(patent).model_dump(mode="json"),
        "segmentation": segment_patent(patent.text or "").as_dict(),
    }


@router.patch("/projects/{project_id}/patents/{patent_id}", response_model=PatentResponse)
async def update_patent(
    project_id: str, patent_id: str, request: UpdatePatentRequest
) -> PatentResponse:
    """Edit a stored patent's text or metadata."""
    _require_project(project_id)
    current = _require_patent(project_id, patent_id)

    # An explicit null means "leave as is"; an empty string clears the field
    # (for a date, "" parses to None and that None is kept on purpose).
    changes = {k: v for k, v in request.model_dump(exclude_unset=True).items() if v is not None}
    if "url" in changes:
        try:
            changes["url"], changes["source"] = validate_public_url(changes["url"])
        except PatentSourceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "text" in changes:
        changes["text"] = changes["text"].strip()

    fields, warnings = _validated_metadata(changes)
    changes.update(fields)

    merged = {**current.model_dump(), **changes}
    _check_dates(merged)
    if not (merged.get("text") or "").strip() and not merged.get("url"):
        raise HTTPException(
            status_code=400,
            detail="A patent needs its text, a public registry link, or both.",
        )

    updated = metadata_store.update_patent(patent_id, **changes)
    if updated is None:
        raise HTTPException(status_code=404, detail="Patent not found")
    return _respond(updated, warnings)


@router.delete("/projects/{project_id}/patents/{patent_id}", status_code=204)
async def delete_patent(project_id: str, patent_id: str) -> None:
    """Remove a stored patent reference."""
    _require_patent(project_id, patent_id)
    metadata_store.delete_patent(patent_id)
