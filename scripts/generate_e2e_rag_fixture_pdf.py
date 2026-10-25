"""Create the deterministic, text-based PDF used by the E2E evaluation case."""

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


OUTPUT = Path("output/pdf/e2e-rag-evaluation-source.pdf")

PAGES = [
    (
        "RAG-001: Retrieval and hallucination",
        "Retrieval-augmented generation reduces hallucination by retrieving relevant passages "
        "before an answer is generated. The retrieved evidence constrains the answer to what "
        "the source supports instead of encouraging unsupported claims.",
    ),
    (
        "RAG-002: Dense similarity retrieval",
        "Dense vector representations support similarity search over an embedding index. "
        "Similarity ranking selects passages whose meaning is close to the question before "
        "generation begins.",
    ),
    (
        "RAG-003: Grounding in external knowledge",
        "Grounding an answer in external knowledge improves factual accuracy because generation "
        "can rely on retrieved evidence rather than model parameters alone. External knowledge "
        "makes factual statements traceable to a source.",
    ),
    (
        "TF-001: Parallel self attention",
        "Self attention compares token positions together, so a transformer can process a sequence "
        "in parallel. This removes the sequential dependency imposed by recurrent processing.",
    ),
    (
        "TF-002: Transformer versus recurrent computation",
        "The transformer architecture replaces recurrent computation with attention over the whole "
        "sequence. A recurrent network processes positions in order, while a transformer can attend "
        "across positions directly.",
    ),
    (
        "TF-003: Query, key, and value projections",
        "Each token is projected into query, key, and value vectors. A query compares with keys to "
        "find relevant positions, and the resulting weights combine the corresponding value vectors.",
    ),
    (
        "CMP-001: Training efficiency",
        "A transformer avoids the recurrent dependency that limits parallel hardware use. Compared "
        "with recurrent neural networks, this enables faster training when many sequence positions "
        "are processed concurrently.",
    ),
    (
        "CMP-002: Retrieval and language models",
        "A retrieval-based language model consults an external corpus at inference time. A purely "
        "parametric language model instead answers from weights learned during training without "
        "retrieval from that corpus.",
    ),
    (
        "KG-001: Knowledge graph support",
        "A knowledge graph connects related entities and concepts. In a retrieval pipeline, graph "
        "traversal can surface related evidence that a dense or lexical match did not retrieve.",
    ),
    (
        "CHK-001: Chunking documents",
        "A document is split into small passages before embedding. Focused passages let retrieval "
        "return the specific evidence needed for a question instead of an entire document.",
    ),
]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(HexColor("#CBD5E1"))
    canvas.line(18 * mm, 17 * mm, 192 * mm, 17 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#475569"))
    canvas.drawString(18 * mm, 11 * mm, "MAIROS deterministic evaluation fixture")
    canvas.drawRightString(192 * mm, 11 * mm, f"Page {doc.page}")
    canvas.restoreState()


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "FixtureTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=25,
        textColor=HexColor("#0F172A"),
        spaceAfter=18,
    )
    body = ParagraphStyle(
        "FixtureBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=12,
        leading=18,
        textColor=HexColor("#1E293B"),
    )
    note = ParagraphStyle(
        "FixtureNote",
        parent=styles["BodyText"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=13,
        textColor=HexColor("#475569"),
    )

    story = []
    for index, (heading, evidence) in enumerate(PAGES, start=1):
        story.extend(
            [
                Paragraph("MAIROS Evaluation Fixture", note),
                Spacer(1, 18 * mm),
                Paragraph(heading, title),
                Paragraph(evidence, body),
                Spacer(1, 12 * mm),
                Paragraph(
                    "This page intentionally contains the evaluation evidence for one curated "
                    "golden-set case. It is synthetic test content, not a research publication.",
                    note,
                ),
            ]
        )
        if index < len(PAGES):
            story.append(PageBreak())

    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=24 * mm,
        title="MAIROS E2E RAG Evaluation Source",
        author="MAIROS test fixture",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    main()
