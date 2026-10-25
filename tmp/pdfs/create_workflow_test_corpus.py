from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfgen import canvas


OUTPUT = Path(
    r"C:\Users\moort\SEM THREE\AI_ML\Project\mairos\output\pdf\mairos-workflow-test-corpus-10-pages.pdf"
)

# Invented excerpts sized to stay below MAIROS's default 512-character chunk
# target after the real PDF extractor reads the headings and page furniture.
PAGES = [
    {
        "study": "SYNTHETIC STUDY A | PASSAGE-GROUNDED ANSWERING",
        "title": "Retrieval and hallucination in research Q&A",
        "sections": [
            ("Question", "Can retrieval-augmented generation reduce hallucination in research Q&A?"),
            ("Method", "Retrieve external knowledge passages before a language model drafts an answer."),
            ("Finding", "Cited evidence helps readers check factual claims."),
        ],
    },
    {
        "study": "SYNTHETIC STUDY A | RETRIEVAL METHOD",
        "title": "Dense similarity search for paper passages",
        "sections": [
            ("Method", "Dense vector similarity search ranks passages by semantic match to a question."),
            ("Finding", "Retrieved context can improve factual accuracy over model weights alone."),
            ("Limitation", "Different wording may hide a relevant result."),
        ],
    },
    {
        "study": "SYNTHETIC STUDY B | GRAPH-GUIDED RETRIEVAL",
        "title": "Connecting concepts across research papers",
        "sections": [
            ("Question", "Can a knowledge graph surface evidence that dense similarity search misses?"),
            ("Method", "Link papers and concepts, then retrieve passages attached to nearby concepts."),
            ("Finding", "Graph traversal can connect a topic to a method or result."),
        ],
    },
    {
        "study": "SYNTHETIC STUDY B | COMPARISON AND LIMITATIONS",
        "title": "Hybrid retrieval and graph coverage",
        "sections": [
            ("Comparison", "Vector search finds semantic matches; graph traversal can boost linked chunks."),
            ("Limitation", "Sparse or incorrect graph links can hide evidence. Thin graph coverage does not show field-wide absence."),
            ("Open question", "How do graph upkeep costs compare with retrieval gains?"),
        ],
    },
    {
        "study": "SYNTHETIC STUDY C | DOCUMENT INGESTION",
        "title": "Chunking long papers into specific passages",
        "sections": [
            ("Question", "How should a paper be split into retrieval units?"),
            ("Method", "Extract page text, split it into short passages, and embed each passage."),
            ("Limitation", "A chunk boundary can separate a claim from its caveat."),
        ],
    },
    {
        "study": "SYNTHETIC STUDY D | TRANSFORMER ARCHITECTURE",
        "title": "Self attention and parallel sequence processing",
        "sections": [
            ("Method", "A transformer replaces recurrent computation with self attention over sequence positions."),
            ("Finding", "Self attention allows parallel processing and faster training than recurrence."),
            ("Limitation", "Long sequences use more memory."),
        ],
    },
    {
        "study": "SYNTHETIC STUDY D | ATTENTION MECHANISM",
        "title": "Query, key, and value projections",
        "sections": [
            ("Method", "Tokens become query, key, and value vectors; query-key similarity sets weights over values."),
            ("Finding", "Weighted values combine information across the sequence."),
            ("Limitation", "Attention does not retrieve documents or prove an answer true."),
        ],
    },
    {
        "study": "SYNTHETIC STUDY E | KNOWLEDGE SOURCES",
        "title": "Retrieval versus a parametric language model",
        "sections": [
            ("Comparison", "Retrieval systems consult an external corpus; a parametric language model answers from learned weights."),
            ("Finding", "External passages can provide updateable evidence and citations."),
            ("Limitation", "Answers depend on corpus coverage and ranking."),
        ],
    },
    {
        "study": "SYNTHETIC CROSS-PAPER COMPARISON",
        "title": "Methods, evidence, and reported limitations",
        "sections": [
            ("Study A", "Uses passages to ground answers and reduce hallucination."),
            ("Study B", "Combines dense similarity and graph traversal."),
            ("Study C", "Studies chunking; passages may split a claim from its caveat."),
        ],
    },
    {
        "study": "SYNTHETIC OPEN-PROBLEM EXCERPT",
        "title": "Evidence-backed gaps for a follow-up test",
        "sections": [
            ("Open gaps", "Test paraphrased citations, graph upkeep, retrieval latency, and chunk boundaries that split claims from limits."),
            ("Evaluation", "Use these synthetic excerpts to practice comparison and retrieval evaluation."),
            ("Scope", "All studies are invented, not published or field-wide evidence."),
        ],
    },
]


def draw_page(c: canvas.Canvas, page_no: int, data: dict) -> None:
    width, height = letter
    c.setFillColor(colors.HexColor("#F7F8F5"))
    c.rect(0, 0, width, height, fill=1, stroke=0)

    c.setFillColor(colors.HexColor("#007F73"))
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(60, height - 43, "MAIROS WORKFLOW TEST CORPUS  |  SYNTHETIC DATA")
    c.setFillColor(colors.HexColor("#65756F"))
    c.setFont("Helvetica", 8.5)
    c.drawRightString(width - 60, height - 43, f"PAGE {page_no:02d} / 10")

    c.setStrokeColor(colors.HexColor("#CBD5D0"))
    c.setLineWidth(0.8)
    c.line(60, height - 55, width - 60, height - 55)

    c.setFillColor(colors.HexColor("#007F73"))
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(60, height - 83, data["study"])

    title_style = ParagraphStyle(
        "title",
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=26,
        textColor=colors.HexColor("#172623"),
        spaceAfter=0,
    )
    title = Paragraph(escape(data["title"]), title_style)
    _, title_height = title.wrap(width - 120, 100)
    title.drawOn(c, 60, height - 105 - title_height)

    body_style = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=11.4,
        leading=16,
        textColor=colors.HexColor("#354741"),
        spaceAfter=0,
    )
    y = height - 143 - title_height
    for label, text in data["sections"]:
        paragraph = Paragraph(
            f"<b>{escape(label)}:</b> {escape(text)}",
            body_style,
        )
        _, paragraph_height = paragraph.wrap(width - 120, 190)
        paragraph.drawOn(c, 60, y - paragraph_height)
        y -= paragraph_height + 18

    c.setStrokeColor(colors.HexColor("#CBD5D0"))
    c.line(60, 63, width - 60, 63)
    c.setFillColor(colors.HexColor("#65756F"))
    c.setFont("Helvetica", 8)
    c.drawString(60, 47, "TEST FIXTURE ONLY - NOT PUBLISHED RESEARCH")
    c.drawRightString(width - 60, 47, "Use real papers for scholarly conclusions")
    c.showPage()


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUTPUT), pagesize=letter, pageCompression=1)
    c.setTitle("MAIROS Workflow Test Corpus - 10 Pages")
    c.setAuthor("MAIROS demo fixture")
    c.setSubject("Synthetic corpus for testing retrieval and research workflows")
    for page_no, data in enumerate(PAGES, start=1):
        draw_page(c, page_no, data)
    c.save()
    print(f"Wrote {OUTPUT} ({len(PAGES)} pages)")


if __name__ == "__main__":
    main()
