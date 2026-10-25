from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

OUT = Path('output/pdf')
OUT.mkdir(parents=True, exist_ok=True)
NAVY = colors.HexColor('#17324D')
BLUE = colors.HexColor('#DCEBFA')
GRAY = colors.HexColor('#F2F4F7')
DARK = colors.HexColor('#243447')
RED = colors.HexColor('#9E2A2B')

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='DocTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=19, leading=23, textColor=NAVY, alignment=TA_LEFT, spaceAfter=10))
styles.add(ParagraphStyle(name='SectionX', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=15, textColor=NAVY, spaceBefore=7, spaceAfter=4))
styles.add(ParagraphStyle(name='BodyX', parent=styles['BodyText'], fontName='Helvetica', fontSize=9.2, leading=12.3, textColor=DARK, spaceAfter=5))
styles.add(ParagraphStyle(name='SmallX', parent=styles['BodyText'], fontName='Helvetica', fontSize=8, leading=10.2, textColor=DARK, spaceAfter=3))
styles.add(ParagraphStyle(name='DisclosureX', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=8.2, leading=10, textColor=RED, backColor=colors.HexColor('#FFF0F0'), borderColor=colors.HexColor('#E5A6A6'), borderWidth=.5, borderPadding=6, spaceBefore=4, spaceAfter=8))
styles.add(ParagraphStyle(name='TableHeadX', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=8, leading=9.5, textColor=colors.white))
styles.add(ParagraphStyle(name='TableCellX', parent=styles['BodyText'], fontName='Helvetica', fontSize=8, leading=10, textColor=DARK))


def P(text, style='BodyX'):
    return Paragraph(text, styles[style])

def make_table(rows, widths):
    cooked=[]
    for ri,row in enumerate(rows):
        cooked.append([P(str(v), 'TableHeadX' if ri == 0 else 'TableCellX') for v in row])
    t=Table(cooked, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY),
        ('BACKGROUND',(0,1),(-1,-1),colors.white),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,GRAY]),
        ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#C8D0D8')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))
    return t

def page_marks(label):
    def draw(canvas, doc):
        canvas.saveState()
        w,h=letter
        canvas.setFillColor(NAVY); canvas.rect(0,h-0.32*inch,w,0.32*inch,stroke=0,fill=1)
        canvas.setFillColor(colors.white); canvas.setFont('Helvetica-Bold',8)
        canvas.drawString(0.62*inch,h-0.22*inch,'MAIROS - SYNTHETIC TEST CORPUS')
        canvas.setFillColor(colors.HexColor('#64748B')); canvas.setFont('Helvetica',7.5)
        canvas.drawString(0.62*inch,0.38*inch,label)
        canvas.drawRightString(w-0.62*inch,0.38*inch,f'Page {doc.page}')
        canvas.restoreState()
    return draw

def build(filename, title, subtitle, page1, page2):
    path=OUT/filename
    doc=SimpleDocTemplate(str(path),pagesize=letter,rightMargin=.62*inch,leftMargin=.62*inch,topMargin=.55*inch,bottomMargin=.58*inch,title=title,author='MAIROS synthetic workflow test data',subject='Fictional test data; not published research')
    story=[P(title,'DocTitle'),P(subtitle,'BodyX'),P('<b>TEST DATA DISCLOSURE:</b> This paper is fictional. All study descriptions, sample sizes, measurements, and results below are invented solely to test MAIROS workflows. Do not cite as published research.','DisclosureX')]
    for heading,body in page1:
        story += [P(heading,'SectionX'), P(body)]
    story.append(PageBreak())
    story += [P(title + ' — results and interpretation','DocTitle'),P('<b>TEST DATA DISCLOSURE:</b> Every value on this page is invented illustrative data, not a real empirical finding.','DisclosureX')]
    for item in page2:
        if isinstance(item, tuple) and item[0]=='table':
            story.append(make_table(item[1], item[2]))
            story.append(Spacer(1,6))
        else:
            heading,body=item
            story += [P(heading,'SectionX'),P(body)]
    doc.build(story,onFirstPage=page_marks('Fictional workflow fixture - not a scholarly source'),onLaterPages=page_marks('Fictional workflow fixture - not a scholarly source'))
    print(path, path.stat().st_size)

build(
 'synthetic-paper-a-grounded-generation.pdf',
 'Synthetic Paper A: Evidence-Grounded Generation for Scientific Q&A',
 'Fixture ID SYN-A - Version 1.0 - Intended for project-level retrieval and paper comparison',
 [
  ('Abstract', 'This fictional study tests whether retrieving source passages before generation improves evidence support in scientific question answering. It compares a parametric-only answerer with a retrieval-augmented answerer on a small constructed question set. The purpose here is to supply stable, internally consistent test passages for upload, retrieval, comparison, gap analysis, and evaluation workflows.'),
  ('Research question and hypothesis', 'RQ-A: On questions whose answers appear in a supplied evidence collection, does retrieval-augmented generation increase the proportion of factual claims supported by a cited passage compared with a parametric-only baseline? H-A: retrieval-augmented generation will increase supported-claim rate. This is a fictional, testable hypothesis, not an established result.'),
  ('Methods', 'The fixture describes 100 synthetic scientific questions with one short evidence passage per question. Two answer conditions are compared: (1) Parametric-only, with no passage supplied at answer time; and (2) Retrieve-then-generate, with the top five passages from the fixture collection available to the generator. Two human-review-style labels are represented as invented counts: supported answer means the central factual claim is entailed by a retrieved passage; citation entailment means the cited passage directly supports the claim.'),
  ('Dataset and controls', 'All 100 question/evidence pairs are invented and cover general methods concepts. The same questions and answer rubric are intended for both conditions. The fixture does not contain real participant data, a real benchmark, or a real model run. It does not establish statistical significance or generalization to real scientific literature.'),
 ],
 [
  ('table',[
   ['Measure (invented)', 'Parametric-only', 'Retrieve-then-generate'],
   ['Central claim supported', '62 / 100 (62%)', '81 / 100 (81%)'],
   ['Citation entails claim', 'Not applicable: no citations', '74 / 100 (74%)'],
   ['Unsupported central claim', '38 / 100 (38%)', '19 / 100 (19%)'],
  ],[2.2*inch,2.15*inch,2.35*inch]),
  ('Illustrative interpretation', 'Within this fictional fixture, the retrieval condition has a higher supported-claim count than the parametric-only condition. The difference is a convenient positive signal for checking whether MAIROS retrieves passages about evidence grounding and whether the answer flow can cite them. It must not be reported as a real research result.'),
  ('Limitations and open questions', 'The constructed questions are small and synthetic; no real corpus, model, annotator agreement, confidence interval, or cost measurement is provided. Citation entailment is lower than supported-answer rate in the invented counts, leaving a test gap: can citation checking identify unsupported citations, especially when a relevant passage is paraphrased? A follow-up test could vary retrieval depth and paraphrase distance while holding questions fixed.'),
  ('Comparison hooks', 'Compare SYN-A with SYN-B on the role of graph links and retrieval quality, and with SYN-C on document segmentation. Distinguish each paper’s research question, intervention, data, metric, limitation, and evidence. The values in all three fixtures are invented, so compare them as application test cases only.'),
 ])

build(
 'synthetic-paper-b-graph-retrieval.pdf',
 'Synthetic Paper B: Graph-Guided Retrieval for Multi-Hop Questions',
 'Fixture ID SYN-B - Version 1.0 - Intended for project-level retrieval and paper comparison',
 [
  ('Abstract', 'This fictional study describes graph-guided retrieval for questions requiring connections between multiple concepts. It contrasts dense retrieval alone with dense retrieval followed by a small entity-link traversal. Its invented results and limitations give the MAIROS graph, task, comparison, and research-gap workflows structured content to find.'),
  ('Research question and hypothesis', 'RQ-B: Does adding graph-neighbor passages to dense retrieval improve Recall@5 for multi-hop questions, and what latency trade-off does it introduce? H-B: graph-guided retrieval increases Recall@5 while increasing median latency. The claim is intentionally narrow and fictional.'),
  ('Methods', 'The fixture uses 80 synthetic multi-hop questions and 40 synthetic paper summaries. Dense-only ranks passages by embedding similarity. Graph-guided retrieval first takes dense top-3 results, follows one entity/concept edge, adds up to two neighboring passages, then reranks the candidate set. Both methods use the same question set, source summaries, and top-five evaluation cutoff.'),
  ('Dataset and measures', 'Invented measures are Recall@5 (whether a gold evidence passage appears among the first five results) and median retrieval latency in seconds. The described graph has manually assigned synthetic concept and paper nodes. It does not represent a real knowledge graph or real indexed literature.'),
 ],
 [
  ('table',[
   ['Measure (invented)', 'Dense-only', 'Dense + graph neighbors'],
   ['Recall@5', '0.62', '0.78'],
   ['Median latency', '0.42 s', '0.68 s'],
   ['Gold evidence found', '50 / 80 questions', '62 / 80 questions'],
  ],[2.2*inch,2.15*inch,2.35*inch]),
  ('Illustrative interpretation', 'In this fictional fixture, graph expansion finds more gold evidence passages within five results and takes longer. The numbers are internally aligned (62/80 = 0.775, rounded to 0.78). They exist to make the workflow compare meaningful fields and to help inspect concept-to-paper links.'),
  ('Limitations and open questions', 'The graph is small and manually constructed; entity-link mistakes, missing edges, and graph incompleteness are not measured. Only one traversal depth and one top-five cutoff are described. Open questions include whether the recall gain remains when edges are noisy, whether a two-hop traversal adds enough coverage to justify its latency, and whether gains hold on independently authored real papers.'),
  ('Comparison hooks', 'SYN-B focuses on cross-concept retrieval and graph expansion; SYN-A focuses on claim support and citation entailment; SYN-C focuses on chunk boundaries. Treat the project knowledge graph as a map of indexed fixture content, not proof that a topic is absent from the broader research field.'),
 ])

build(
 'synthetic-paper-c-adaptive-chunking.pdf',
 'Synthetic Paper C: Section-Aware Chunking for Research Documents',
 'Fixture ID SYN-C - Version 1.0 - Intended for project-level retrieval and paper comparison',
 [
  ('Abstract', 'This fictional study tests whether splitting research documents at section boundaries improves retrieval over fixed-character chunks. It compares a fixed 512-character strategy with a section-aware strategy on constructed paper excerpts. It supplies method, metric, result, and limitation fields for MAIROS comparison, hypotheses, experiment design, and literature-review testing.'),
  ('Research question and hypothesis', 'RQ-C: Do section-aware chunks improve nDCG@5 over fixed-size chunks for questions about research methods and results? H-C: preserving section boundaries will improve nDCG@5, especially when a question targets a complete method or result passage. This remains a fictional hypothesis.'),
  ('Methods', 'The fixture describes 60 synthetic research-paper excerpts. Fixed-size chunks use 512 characters with 64-character overlap. Section-aware chunking splits on headings and paragraphs, with a maximum target of 700 characters and a minimum of 120 characters. Both conditions use the same fictional query set, embedding model description, and ranking cutoff.'),
  ('Dataset and measure', 'The invented primary measure is nDCG@5, averaged across the 60 constructed questions using fictional relevance labels. A secondary measure is multi-sentence answer-evidence recall: whether all sentences marked as needed for an answer appear within the top five passages. No actual model or benchmark was run.'),
 ],
 [
  ('table',[
   ['Measure (invented)', 'Fixed 512-char chunks', 'Section-aware chunks'],
   ['Mean nDCG@5', '0.71', '0.75'],
   ['Complete evidence in top five', '34 / 60 questions', '40 / 60 questions'],
   ['Median chunks per document', '18', '16'],
  ],[2.2*inch,2.15*inch,2.35*inch]),
  ('Illustrative interpretation', 'In this fictional fixture, section-aware chunks score higher on both invented retrieval measures and create fewer median chunks per document. These numbers are only fixture values for validating that MAIROS can index and retrieve content about chunking and can distinguish reported results from unsupported conclusions.'),
  ('Limitations and open questions', 'All excerpts and relevance judgments are synthetic. The section parser is assumed to recognize headings and paragraphs; tables, equations, scanned pages, and irregular layouts are not evaluated. Open questions include how robust the gain is when headings are missing or misleading, how to select a maximum chunk length, and whether the same trade-off appears in multilingual or full-length real papers.'),
  ('Comparison hooks', 'SYN-C concerns document segmentation; SYN-A concerns supported answer generation; SYN-B concerns graph-guided multi-hop retrieval. A reasonable test gap across the set is interaction: whether graph traversal still helps when chunk boundaries preserve section context. This is a test-design idea inferred from these three fixtures, not a claim about the research field.'),
 ])

