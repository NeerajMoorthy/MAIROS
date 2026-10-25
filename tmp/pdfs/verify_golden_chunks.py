from pathlib import Path
from services.ingestion.pipeline import IngestionPipeline
from services.evaluation.golden_set import GoldenSet
p = IngestionPipeline(chunk_size=512, chunk_overlap=64, chroma_store=None)
pdf = Path('output/pdf/mairos-workflow-test-corpus-10-pages.pdf')
pages = p.extractor.extract(pdf)
chunks = []
for page in pages:
    chunks.extend(p.chunker.chunk(page.text, page=page.page_number, document_name=pdf.name))
golden = GoldenSet()
missing=[]
for case in golden:
    if not any(case.is_relevant({'text': chunk.text, 'document_name': pdf.name}) for chunk in chunks):
        missing.append(case.id)
print(f'pages={len(pages)} actual_chunks={len(chunks)} golden_cases={len(golden)} unsupported={missing}')
