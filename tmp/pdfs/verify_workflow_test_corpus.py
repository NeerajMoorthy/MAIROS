import json
import sys
from pathlib import Path

repo = Path(r"C:\Users\moort\SEM THREE\AI_ML\Project\mairos")
pdf = repo / "output" / "pdf" / "mairos-workflow-test-corpus-10-pages.pdf"
sys.path.insert(0, str(repo))

from services.evaluation.golden_set import GoldenSet
from services.ingestion.pipeline import IngestionPipeline

pipeline = IngestionPipeline(chunk_size=512, chunk_overlap=64)
pages = pipeline.extractor.extract(pdf)
summary = pipeline.ingest(pdf, project_id="verification-only")

chunks = []
for page in pages:
    chunks.extend(pipeline.chunker.chunk(page.text, page=page.page_number))

golden_set = GoldenSet()
coverage = {
    case.id: any(case.is_relevant({"text": chunk.text}) for chunk in chunks)
    for case in golden_set.cases
}

report = {
    "pdf": str(pdf),
    "pages": len(pages),
    "page_character_counts": [len(page.text) for page in pages],
    "chunker": {"chunk_size": 512, "chunk_overlap": 64},
    "chunks": len(chunks),
    "chunks_per_page": {
        page.page_number: len(pipeline.chunker.chunk(page.text, page=page.page_number))
        for page in pages
    },
    "pipeline_summary": summary,
    "golden_cases_supported_by_fixture_terms": sum(coverage.values()),
    "golden_case_count": len(coverage),
    "golden_case_support": coverage,
}
print(json.dumps(report, indent=2))

assert len(pages) == 10, f"Expected 10 pages, got {len(pages)}"
assert summary["num_chunks"] == 10, f"Project pipeline returned {summary['num_chunks']} chunks"
assert len(chunks) == 10, f"Direct project chunker returned {len(chunks)} chunks"
assert all(n == 1 for n in report["chunks_per_page"].values()), "Expected exactly one chunk per page"
assert all(coverage.values()), "Some curated evaluation cases have no relevant fixture chunk"
