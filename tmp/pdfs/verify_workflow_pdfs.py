from pathlib import Path
from services.ingestion.pipeline import IngestionPipeline
from services.evaluation.golden_set import GoldenSet

pipeline = IngestionPipeline(chunk_size=512, chunk_overlap=64, chroma_store=None)
for path in sorted(Path('output/pdf').glob('*.pdf')):
    if path.name == 'e2e-rag-evaluation-source.pdf':
        continue
    result = pipeline.ingest(path, project_id='manual-workflow-test')
    print(f"{path.name}: pages={result['num_pages']}, chunks={result['num_chunks']}, title={result['title']}")

corpus = Path('output/pdf/mairos-workflow-test-corpus-10-pages.pdf')
result = pipeline.ingest(corpus, project_id='manual-workflow-test')
print(f"EVALUATION CORPUS: pages={result['num_pages']}, chunks={result['num_chunks']}")
chunks = pipeline.extractor.extract(corpus)
all_text = '\n'.join(page.text for page in chunks)
golden = GoldenSet()
for case in golden:
    normalized = ' '.join(all_text.lower().split())
    # Reproduce the term_match policy across all page chunks.
    hit = any(case.is_relevant({'text': page.text, 'document_name': corpus.name}) for page in chunks)
    print(f"golden {case.id}: {'SUPPORTED' if hit else 'MISSING'} | {case.question}")
