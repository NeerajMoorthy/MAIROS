"""The "RailGuard Lite" sample project: the walkthrough's files and the example workspace.

Used by ``scripts/generate_sample_project.py`` (writes the files for
docs/SAMPLE_PROJECT_WALKTHROUGH.md) and by Settings -> *Load example data*
(``apps/api/app/routers/workspace.py``), so the files a tester downloads and
the project the app loads are the same.

The sample project is a low-cost railway crack-detection robot. Its files:

- three short sample papers (PDF, two pages each) on three ways of finding
  rail defects — camera images, ultrasonic guided waves, and vibration. They
  are fictional: authors, data and results are invented, and a note on each
  first page says so. Each states its results, a limitation and an open
  question in plain sentences, so every workflow has something checkable to
  find;
- the project description for *Review my project*, and a fictional patent text
  for the Patents page;
- two files that must be refused: an image-only "scanned" PDF and a text file
  renamed to .pdf.

The papers are set in the PDF base fonts (Helvetica), which have no ligatures:
a font that joins "fl" into one glyph would make "flagged" extract as
"\\ufb02agged" and stop matching the word a tester types.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

PAGE = pymupdf.paper_rect("a4")
MARGIN = 60
WIDTH = PAGE.width - 2 * MARGIN
FIXED_DATE = "D:20261025000000"

# Each paper: (file name, title, authors, year, page 1 sections, page 2
# sections). A section is (heading, text); the heading is set on its own line
# and ends with a full stop, so it never runs into the next sentence when the
# text is split into sentences. Words that the gap finder treats as cues
# ("limitation", "future work", "remains", "however", "challenge", "open
# problem") appear only in the sentences that state a gap.
PAPERS = [
    (
        "paper-a-camera-cnn.pdf",
        "Lightweight CNN Crack Detection on Rail Heads",
        "A. Rao and M. Chen", 2024,
        [
            ("Abstract", "We test whether a lightweight convolutional neural network (CNN) running on a "
             "single-board computer can find surface cracks on rail heads from camera images. "
             "On our test set the network found 91% of cracked images in daylight."),
            ("Method", "A downward-facing camera on a push trolley photographs the rail head every 5 cm. "
             "Each 224 by 224 pixel image is classified as cracked or intact by a MobileNet-style CNN "
             "with 1.2 million parameters. The model runs on a Raspberry Pi 4 at 14 frames per second, "
             "so no cloud connection is needed."),
            ("Data", "We collected 2,400 rail-head images on a 2 km test line, of which 600 show cracks "
             "wider than 0.5 mm. The images were split 70/15/15 into training, validation and test sets."),
        ],
        [
            ("Results", "On the daylight test set the CNN reached a recall of 0.91 and a precision of 0.88. "
             "On 300 images taken at dusk, recall fell to 0.64. Cracks narrower than 0.5 mm were found "
             "in only 22% of cases."),
            ("Limitations", "A limitation of this study is that all training images were captured in daylight, "
             "so performance at night or in rain is unknown. The trolley was pushed at walking speed, and "
             "motion blur at higher speeds was not measured."),
            ("Open questions", "It remains unclear whether infrared illumination can restore recall at night. "
             "Future work should pair the camera with a second sensor that does not depend on light."),
            ("Conclusion", "A small CNN on a single-board computer can flag visible rail-head cracks in "
             "daylight without a cloud connection."),
        ],
    ),
    (
        "paper-b-ultrasonic-guided-waves.pdf",
        "Ultrasonic Guided Waves for Rail Weld Flaws",
        "L. Okafor and S. Iyer", 2023,
        [
            ("Abstract", "We evaluate ultrasonic guided waves for finding internal flaws in the thermite welds "
             "of continuous rail. Guided waves detected 95% of flaws that were 2 mm deep or more."),
            ("Method", "Two piezoelectric transducers clamped to the rail foot send 50 kHz guided waves along "
             "the rail, and a flaw reflects part of each wave back. The arrival time of the echo locates "
             "the flaw to within 15 cm."),
            ("Data", "We tested 120 welds on a decommissioned line. Of these, 40 contained machined flaws "
             "between 1 mm and 6 mm deep, and 80 were intact."),
        ],
        [
            ("Results", "Guided waves detected 38 of the 40 flawed welds (95%) and raised 3 false alarms on the "
             "80 intact welds. A crew inspected 1 km of track in about 40 minutes. Flaws shallower than "
             "2 mm were missed in 7 of 12 cases."),
            ("Limitations", "The main limitation is that the transducers need direct contact with the rail and a "
             "gel couplant, which slows inspection. Surface cracks on the rail head were outside the scope "
             "of this test."),
            ("Open questions", "Future work should test whether guided-wave results can be combined with camera "
             "images of the same rail section. It remains unknown how well the method works on curved track."),
            ("Conclusion", "Guided waves find deep internal weld flaws reliably, but they are slow to deploy."),
        ],
    ),
    (
        "paper-c-vibration-alerts.pdf",
        "Vibration Monitoring and GPS Alerts for Track Defects",
        "P. Novak and R. Das", 2025,
        [
            ("Abstract", "We study whether accelerometers on an inspection trolley can flag track defects and "
             "report their location in real time. The system flagged 87% of known defects with a median "
             "alert delay of 9 seconds."),
            ("Method", "Two MEMS accelerometers sampling at 2 kHz are mounted on the trolley axle. An anomaly "
             "score compares each 0.5 s window with a rolling baseline, and windows above a threshold "
             "trigger an alert. A GSM module sends each alert as a text message with the GPS position."),
            ("Data", "Trials ran over a 6 km test track with 46 known defects, including cracks, loose "
             "fastenings and dipped joints."),
        ],
        [
            ("Results", "The system flagged 40 of the 46 defects (87%) and raised about one false alarm every "
             "3 km. The median delay from passing a defect to the alert arriving was 9 seconds. Weak GSM "
             "coverage delayed 12% of alerts by more than one minute."),
            ("Limitations", "A limitation of this study is that it used a single 6 km test track, so the "
             "false-alarm rate may not hold on busy mainline routes. Vibration alone could not tell a crack "
             "from a loose fastening."),
            ("Open questions", "An open problem is how to fuse vibration alerts with visual confirmation to cut "
             "false alarms. Future work should also test alert delivery where there is no GSM signal."),
            ("Conclusion", "Low-cost accelerometers can flag defects and send located alerts, but they need a "
             "second sensor to classify what they found."),
        ],
    ),
]

PROJECT_DESCRIPTION = """\
RailGuard Lite: a low-cost railway track crack detection robot

Manual inspection of railway tracks is slow and expensive, and small cracks are often missed until they cause a failure. RailGuard Lite is a battery-powered robot that moves along one rail and looks for surface cracks on the rail head. It combines a camera with an infrared sensor, so that it also works at night, and it runs a lightweight crack-detection model on a microcontroller, so it needs no cloud connection. When it finds a crack, a GSM module sends an alert with the GPS location to the maintenance team. We propose a camera and infrared crack detector that runs on a microcontroller. We build an alerting module that sends the GPS position of each crack over GSM. We will test it on a 500 m test track with artificial cracks between 0.5 mm and 3 mm wide.
"""

PATENT = """\
FICTIONAL PATENT TEXT, written for testing MAIROS. It is not a real patent.

Type this into the Title box:
Rail inspection trolley with camera and vibration sensing

Paste everything between the two lines below into the Text box.
------------------------------------------------------------------------
Abstract: A trolley inspects railway track using a camera and an axle-mounted accelerometer, and reports suspected defects together with their GPS position.

Claims:
1. A rail inspection trolley comprising a camera directed at the rail head, an accelerometer mounted on an axle of the trolley, and a processor that classifies camera images of the rail head as cracked or intact.
2. The trolley of claim 1, wherein the processor is a single-board computer running a convolutional neural network.
3. The trolley of claim 1, wherein the accelerometer samples at not less than 1 kHz and an anomaly score is computed for each window of samples.
4. The trolley of claim 3, further comprising a GSM module that sends an alert containing a GPS position when the anomaly score exceeds a threshold.
------------------------------------------------------------------------
"""

SCANNED_TEXT = (
    "Inspection log, rail section 14B.\n\n"
    "This page was scanned from paper, so it holds a picture of text and no text layer. "
    "MAIROS has no OCR, so uploading this file must be refused with a message saying so."
)

BROKEN_FILE = (
    "This is a plain text file renamed to .pdf, for testing how MAIROS handles a file "
    "that is not a PDF. Uploading it must fail with a readable error.\n"
)


def _block(page, y: float, text: str, font: str, size: float, space_after: float) -> float:
    """Set ``text`` in a box starting at ``y``; return where the next block starts."""
    box = pymupdf.Rect(MARGIN, y, MARGIN + WIDTH, PAGE.height - MARGIN)
    unused = page.insert_textbox(box, text, fontname=font, fontsize=size, lineheight=1.35)
    if unused < 0:
        raise ValueError(f"text does not fit on the page: {text[:40]!r}")
    return box.y1 - unused + space_after


def render_paper(title: str, authors: str, year: int, page_one: list, page_two: list) -> bytes:
    """A two-page paper as PDF bytes; the second page starts at the results."""
    if pymupdf.get_text_length(title, fontname="hebo", fontsize=15) > WIDTH:
        raise ValueError(f"title wraps, so it would be misread: {title!r}")
    note = (
        f"A fictional sample paper by {authors} ({year}), written to test MAIROS. "
        "It is not published research: its data and results are invented."
    )
    doc = pymupdf.open()
    for number, sections in enumerate((page_one, page_two), start=1):
        page = doc.new_page(width=PAGE.width, height=PAGE.height)
        y = MARGIN
        if number == 1:
            y = _block(page, y, title, "hebo", 15, 12)
        for heading, text in sections:
            y = _block(page, y, f"{heading}.", "hebo", 11, 2)
            y = _block(page, y, text, "helv", 11, 10)
        if number == 1:
            y = _block(page, y, "Note.", "hebo", 10, 2)
            _block(page, y, note, "heit", 10, 0)
    doc.set_metadata({
        "title": title,
        "author": f"{authors} (fictional)",
        "subject": "Fictional sample paper for testing MAIROS; not published research.",
        "creator": "services/samples/railguard.py",
        "producer": "PyMuPDF",
        "creationDate": FIXED_DATE,
        "modDate": FIXED_DATE,
    })
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data


def write_paper(path: Path, title: str, authors: str, year: int, page_one: list, page_two: list) -> int:
    """Write a two-page paper; return its page count."""
    path.write_bytes(render_paper(title, authors, year, page_one, page_two))
    return 2


def render_scanned() -> bytes:
    """An image-only page: the text is drawn, rendered to a picture, and only
    the picture is kept — what a scanner produces."""
    source = pymupdf.open()
    page = source.new_page(width=PAGE.width, height=PAGE.height)
    page.insert_textbox(PAGE + (MARGIN, MARGIN, -MARGIN, -MARGIN), SCANNED_TEXT, fontsize=13, fontname="helv")
    picture = page.get_pixmap(dpi=110).tobytes("png")
    source.close()

    scanned = pymupdf.open()
    scanned.new_page(width=PAGE.width, height=PAGE.height).insert_image(PAGE, stream=picture)
    scanned.set_metadata({"creationDate": FIXED_DATE, "modDate": FIXED_DATE})
    data = scanned.tobytes(garbage=3, deflate=True)
    scanned.close()
    return data


def write_scanned(path: Path) -> None:
    path.write_bytes(render_scanned())


# ---------------------------------------------------------------------------
# The example workspace (Settings -> Load example data)
# ---------------------------------------------------------------------------
EXAMPLE_PROJECT_NAME = "RailGuard Lite (example)"
EXAMPLE_PROJECT_DESCRIPTION = (
    "Example workspace: three fictional papers on railway crack detection and a "
    "fictional patent, loaded from Settings so every feature can be tried. "
    "Not real research; use it only to test MAIROS."
)

# The patent as the Patents form takes it: the title, and the text between the
# two rules of PATENT.
PATENT_TITLE = "Rail inspection trolley with camera and vibration sensing"
PATENT_TEXT = PATENT.split("-" * 72 + "\n")[1].strip()

# Downloadable files, in the order Settings lists them: (name, media type,
# what it is for).
SAMPLE_FILES = [
    ("paper-a-camera-cnn.pdf", "application/pdf", "Sample paper: camera images and a small CNN."),
    ("paper-b-ultrasonic-guided-waves.pdf", "application/pdf", "Sample paper: ultrasonic inspection of rail welds."),
    ("paper-c-vibration-alerts.pdf", "application/pdf", "Sample paper: vibration sensing with GPS alerts."),
    ("project-description.txt", "text/plain; charset=utf-8", "Paste into Review my project."),
    ("patent-sample.txt", "text/plain; charset=utf-8", "A fictional patent for the Patents page."),
    ("scanned-page.pdf", "application/pdf", "Image-only PDF: the upload must be refused (no OCR)."),
    ("broken-file.pdf", "application/pdf", "A text file renamed to .pdf: the upload must fail with a clear error."),
]


# What to try in the example workspace, feature by feature, with an input that
# has a known answer in the sample papers (see the walkthrough for details).
# ``where`` is the workspace tab ("search", "chat", "workflows") or "patents";
# ``flow`` names the workflow card an input belongs to.
EXAMPLE_GUIDE = [
    {
        "feature": "Topic search",
        "where": "search",
        "flow": None,
        "input": "railway track crack detection deep learning",
        "expect": "Related papers from arXiv, OpenAlex and Semantic Scholar, each with its source and a link. Needs the internet.",
    },
    {
        "feature": "Upload files",
        "where": "search",
        "flow": None,
        "input": "",
        "expect": "The three papers are already indexed. Download scanned-page.pdf or broken-file.pdf below and upload them: both must be refused with a clear message.",
    },
    {
        "feature": "Chat & Q&A",
        "where": "chat",
        "flow": None,
        "input": "What recall and precision did the lightweight CNN reach in daylight, and what happened at dusk?",
        "expect": "Recall 0.91 and precision 0.88 in daylight, recall 0.64 at dusk, citing paper A, page 2.",
    },
    {
        "feature": "Review my project",
        "where": "workflows",
        "flow": "project",
        "input": PROJECT_DESCRIPTION.strip(),
        "expect": "Your project as read (two stated contributions), the papers searched, coverage per contribution and the gaps. Needs the internet; takes 1-2 minutes.",
    },
    {
        "feature": "Compare papers",
        "where": "workflows",
        "flow": "compare",
        "input": "Compare the detection methods, accuracy and inspection speed of the three papers",
        "expect": "A table across the three papers where every cell cites its paper and page.",
    },
    {
        "feature": "Detect research gaps",
        "where": "workflows",
        "flow": "gaps",
        "input": "Limitations of the camera, ultrasonic and vibration methods",
        "expect": "Gaps quoted from the papers, e.g. daylight-only training images (A), contact transducers (B), a single test track (C).",
    },
    {
        "feature": "Generate hypotheses",
        "where": "workflows",
        "flow": "hypothesis",
        "input": "What hypotheses follow from the gaps in this literature?",
        "expect": "One testable hypothesis per gap, each keeping the gap's citation.",
    },
    {
        "feature": "Design experiments",
        "where": "workflows",
        "flow": "experiment",
        "input": "Budget: one 500 m test track, two weeks, no cloud computing.",
        "expect": "One design per hypothesis: objective, datasets, baselines, deciding metric, procedure and threats to validity.",
    },
    {
        "feature": "Check what is new here",
        "where": "workflows",
        "flow": "novelty",
        "input": "A lightweight CNN running on a single-board computer detects rail-head cracks from camera images.",
        "expect": "Already covered by this project's sources (about 92% overlap, paper A page 1). Try 'Drone-mounted LiDAR maps ballast erosion along the track.' for a claim that is not covered.",
    },
    {
        "feature": "Literature review",
        "where": "workflows",
        "flow": "review",
        "input": "Low-cost sensors for railway track crack detection",
        "expect": "Finds and indexes papers on the topic, compares them in a cited table and reports what is new to this project. Needs the internet.",
    },
    {
        "feature": "Patent awareness",
        "where": "workflows",
        "flow": "patent",
        "input": "Which concepts in this project overlap the stored patent text?",
        "expect": "Overlaps with the fictional trolley patent (already on the Patents page), down to the claim, each with a similarity score. Never a legal opinion.",
    },
]


def paper_files() -> list[tuple[str, bytes]]:
    """The three papers the example workspace indexes, as (file name, PDF bytes)."""
    return [
        (name, render_paper(title, authors, year, page_one, page_two))
        for name, title, authors, year, page_one, page_two in PAPERS
    ]


def sample_file(name: str) -> bytes:
    """One of :data:`SAMPLE_FILES` by name; ``KeyError`` for any other name."""
    for paper in PAPERS:
        if paper[0] == name:
            return render_paper(*paper[1:])
    texts = {
        "project-description.txt": PROJECT_DESCRIPTION,
        "patent-sample.txt": PATENT,
        "broken-file.pdf": BROKEN_FILE,
    }
    if name in texts:
        return texts[name].encode("utf-8")
    if name == "scanned-page.pdf":
        return render_scanned()
    raise KeyError(name)


def build(out: Path) -> list[tuple[Path, str]]:
    """Write every sample file into *out*; return (path, detail) per file."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, title, authors, year, page_one, page_two in PAPERS:
        pages = write_paper(out / name, title, authors, year, page_one, page_two)
        written.append((out / name, f"{pages} pages"))
    for name, text in (
        ("project-description.txt", PROJECT_DESCRIPTION),
        ("patent-sample.txt", PATENT),
        ("broken-file.pdf", BROKEN_FILE),
    ):
        (out / name).write_text(text, encoding="utf-8", newline="\n")
        written.append((out / name, f"{len(text)} characters"))
    write_scanned(out / "scanned-page.pdf")
    written.append((out / "scanned-page.pdf", "image only"))
    return written
