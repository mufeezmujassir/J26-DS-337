from __future__ import annotations

from pathlib import Path
from datetime import datetime
import csv
import json

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(r"C:\Users\MUFEEZ\OneDrive - Sri Lanka Institute of Information Technology\Desktop\RP\Research_2027")
BACKEND = ROOT / "wandaraya-backend"
OUTPUT = ROOT / "output" / "component1"
ASSETS = ROOT / "tmp" / "component1_report_assets"
OUTPUT.mkdir(parents=True, exist_ok=True)
ASSETS.mkdir(parents=True, exist_ok=True)

DOCX_PATH = OUTPUT / "WANDARAYA_Component1_Data_Analysis_and_Project_Audit.docx"

NAVY = "17365D"
BLUE = "2F75B5"
PALE_BLUE = "DDEBF7"
GOLD = "D9A441"
PALE_GOLD = "FFF2CC"
GREEN = "548235"
PALE_GREEN = "E2F0D9"
RED = "C00000"
PALE_RED = "FCE4D6"
GRAY = "666666"
LIGHT_GRAY = "F2F2F2"
BORDER = "D9D9D9"


district_counts = [
    ("Ampara", 464), ("Anuradhapura", 4), ("Badulla", 627), ("Batticaloa", 22),
    ("Colombo", 643), ("Galle", 321), ("Gampaha", 419), ("Hambantota", 435),
    ("Jaffna", 6), ("Kalutara", 492), ("Kandy", 451), ("Kegalle", 302),
    ("Kilinochchi", 0), ("Kurunegala", 39), ("Mannar", 0), ("Matale", 2),
    ("Matara", 460), ("Moneragala", 534), ("Mullaitivu", 0), ("Nuwara Eliya", 331),
    ("Polonnaruwa", 2), ("Puttalam", 7), ("Ratnapura", 558), ("Trincomalee", 1),
    ("Vavuniya", 0),
]

category_counts = [
    ("Nature & Landscapes", 1046), ("Religious & Spiritual", 932),
    ("Shopping & Local Markets", 780), ("Family & Recreation", 749),
    ("History & Archaeology", 425), ("Urban & City Attractions", 412),
    ("Photography & Scenic Spots", 382), ("Festivals & Events", 348),
    ("Culture & Heritage", 343), ("Adventure & Outdoor", 327),
    ("Wellness & Ayurveda", 326), ("Tea, Agriculture & Plantation", 240),
    ("Food & Culinary", 199), ("Educational & Learning", 166),
    ("Wildlife & Safari", 91), ("Water & Marine Activities", 78),
    ("Entertainment & Nightlife", 66), ("Beaches & Coastal", 46),
]

activity_counts = [
    ("Sightseeing", 356), ("Spa and Wellness", 336), ("Historical Exploration", 294),
    ("Hiking", 226), ("Museum Visit", 168), ("Photography", 144),
    ("Wildlife Safari", 124), ("Yoga", 98), ("Camping", 74),
    ("Tea Factory Visit", 63), ("Waterfall Visit", 61), ("Scenic Viewpoint", 35),
    ("Educational Visit", 32), ("Swimming", 32), ("Ayurvedic Treatment", 29),
]

coverage = {
    "Coordinates": (6120, 6120),
    "Opening hours": (6096, 6120),
    "Ratings": (4978, 6120),
    "Category mapping": (5005, 6120),
    "Activity mapping": (1713, 6120),
    "Enrichment description": (51, 6120),
}

weather_metrics = {
    "Rainfall MAE (mm/day)": 5.5375,
    "Rainfall RMSE (mm/day)": 13.7632,
    "Min temp MAE (C)": 0.9052,
    "Min temp RMSE (C)": 1.0971,
    "Max temp MAE (C)": 1.3967,
    "Max temp RMSE (C)": 1.6523,
}

objective_rows = [
    ("SO1", "Hybrid tourism knowledge base", "PARTIAL", "6,120 active records; 18 categories; 50 activities; 6,120 indexed points", "Repair district, activity, category and description coverage; complete provenance/licensing checks"),
    ("SO2", "Semantic candidate retrieval", "PARTIAL", "BGE-large-en-v1.5, 1,024-D normalized embeddings, Qdrant retrieval and PostgreSQL hydration", "Create independent query-attraction relevance labels; run lexical baseline and Precision/Recall/NDCG/MRR comparison"),
    ("SO3", "Unified context re-ranking", "PARTIAL", "Weather, time-of-day, holiday/event and seasonality adapters; R0-R3; explanations and abstention", "Integrate and validate Group Emotion as the fifth dimension; calibrate weights; keep production gate closed until validated"),
    ("SO4", "Experimental context evaluation", "PARTIAL", "Frozen protocols, descriptive pilots, exploratory seasonality benchmark and ablation infrastructure", "Complete independent blinded judgments, full R0-R4 ablation, confidence intervals and statistical testing"),
    ("SO5", "Specialized recommendation agent", "PARTIAL", "LangGraph workflow, research endpoint, clarification, verification and session isolation", "Durable checkpoints, cross-component contracts, load/failure/security tests and production authorization"),
    ("SO6", "Mobile recommendation interface", "PARTIAL", "Flutter Component 1 screens and nine selected tests passing", "Complete feedback capture, device/API integration tests, accessibility/usability testing and SUS study"),
]

fr_rows = [
    ("FR1", "Traveller preference processing", "IMPLEMENTED", "Natural-language intent plus interests, activities, travel style, date/time and constraints"),
    ("FR2", "Tourism data management", "IMPLEMENTED", "PostgreSQL/PostGIS attraction, taxonomy, provenance and enrichment tables"),
    ("FR3", "Geographical data management", "IMPLEMENTED", "District references and coordinates for all 6,120 active attractions"),
    ("FR4", "Destination categorization", "PARTIAL", "18 categories exist, but 1,115 active attractions have no category and 4,407 have no activity"),
    ("FR5", "Semantic representation", "IMPLEMENTED", "BAAI/bge-large-en-v1.5 1,024-D normalized vectors"),
    ("FR6", "Candidate destination retrieval", "IMPLEMENTED", "Qdrant candidate IDs are hydrated and filtered against active PostgreSQL rows"),
    ("FR7", "Five-context re-ranking", "PARTIAL", "Four dimensions operate experimentally; Group Emotion is explicitly rejected/deferred"),
    ("FR8", "Receive contextual outputs", "PARTIAL", "Weather and local context services are integrated; Component 3 emotion output is not"),
    ("FR9", "Ranked recommendation generation", "EXPERIMENTAL", "R0-R3 ranks and movement traces are generated; production order is intentionally protected"),
    ("FR10", "Recommendation explanation", "IMPLEMENTED", "Evidence, provenance, missing dimensions, limitations and itinerary reasons are returned"),
    ("FR11", "User feedback collection", "NOT IMPLEMENTED", "No Component 1 feedback endpoint or persistence workflow was found"),
    ("FR12", "Recommendation API", "IMPLEMENTED", "REST/JSON content, time-aware, unified-context and LangGraph research endpoints"),
]

nfr_rows = [
    ("NFR1", "Performance", "NOT YET MET", "Warm pilots can be sub-second, but cold model paths took about 18-40 seconds; no load distribution proves <=2 seconds"),
    ("NFR2", "Recommendation quality", "PENDING", "No independent query-attraction relevance labels for Precision@K, Recall@K, NDCG@K and MRR"),
    ("NFR3", "Reliability/fallback", "PARTIAL", "Null evidence and provider errors do not become false low scores; broader failure recovery remains unverified"),
    ("NFR4", "Scalability", "PARTIAL", "Modular services and batched context calls exist; concurrency, growth and p95 load evidence are pending"),
    ("NFR5", "Clear presentation", "PARTIAL", "Explanations and Flutter screens exist; formal user comprehension/usability evidence is pending"),
    ("NFR6", "Secure API", "PARTIAL", "Research token/session-owner controls exist; local bypass, rate limiting, scoped auth and CORS hardening remain"),
    ("NFR7", "Maintainability", "IMPLEMENTED", "Modular packages, migrations, tests and extensive research documentation are present"),
    ("NFR8", "Data quality", "PARTIAL", "No coordinate or duplicate-place-ID gaps, but taxonomy and enrichment coverage remain incomplete"),
    ("NFR9", "Extensibility", "IMPLEMENTED", "Adapters, schemas, flags and R4 contract support later dimensions without replacing the whole system"),
    ("NFR10", "Interoperability", "PARTIAL", "34 OpenAPI paths and JSON contracts exist; end-to-end contracts with Components 2-4 remain unverified"),
]


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color: str = BORDER, size: str = "6") -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), size)
        node.set(qn("w:color"), color)


def set_cell_margins(cell, top=90, start=100, bottom=90, end=100) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    mar = tc_pr.first_child_found_in("w:tcMar")
    if mar is None:
        mar = OxmlElement("w:tcMar")
        tc_pr.append(mar)
    for tag, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        elem = mar.find(qn(f"w:{tag}"))
        if elem is None:
            elem = OxmlElement(f"w:{tag}")
            mar.append(elem)
        elem.set(qn("w:w"), str(value))
        elem.set(qn("w:type"), "dxa")


def repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def add_page_field(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run()
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = "PAGE"
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.extend([fld_char1, instr_text, fld_char2])


def make_table(doc, headers, rows, widths=None, status_col=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    hdr = table.rows[0]
    repeat_table_header(hdr)
    for i, text in enumerate(headers):
        cell = hdr.cells[i]
        set_cell_shading(cell, NAVY)
        set_cell_border(cell)
        set_cell_margins(cell)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(str(text))
        r.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)
        r.font.size = Pt(8.5)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    for ri, row in enumerate(rows):
        cells = table.add_row().cells
        for ci, value in enumerate(row):
            cell = cells[ci]
            set_cell_border(cell)
            set_cell_margins(cell)
            if ri % 2:
                set_cell_shading(cell, LIGHT_GRAY)
            if status_col is not None and ci == status_col:
                status = str(value)
                fill = PALE_GREEN if status in {"IMPLEMENTED", "COMPLETE"} else PALE_RED if status in {"NOT IMPLEMENTED", "NOT YET MET"} else PALE_GOLD
                set_cell_shading(cell, fill)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.05
            r = p.add_run(str(value))
            r.font.size = Pt(8.2)
            if status_col is not None and ci == status_col:
                r.bold = True
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    if widths:
        for row in table.rows:
            for i, width in enumerate(widths):
                row.cells[i].width = Inches(width)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(9)
    r = p.add_run(text)
    r.italic = True
    r.font.size = Pt(8.5)
    r.font.color.rgb = RGBColor.from_string(GRAY)


def add_picture(doc, path, width=6.3):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(str(path), width=Inches(width))


def add_bullets(doc, items, level=0):
    for item in items:
        p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
        p.paragraph_format.space_after = Pt(3)
        p.add_run(item)


def add_section_title(doc, title):
    doc.add_heading(title, level=1)


def new_page(doc):
    doc.add_page_break()


def build_charts():
    font_path = Path(r"C:\Windows\Fonts\arial.ttf")
    bold_path = Path(r"C:\Windows\Fonts\arialbd.ttf")
    font = ImageFont.truetype(str(font_path), 24)
    small = ImageFont.truetype(str(font_path), 19)
    tiny = ImageFont.truetype(str(font_path), 15)
    bold = ImageFont.truetype(str(bold_path), 30)

    def canvas(title, width=1500, height=850):
        im = Image.new("RGB", (width, height), "white")
        d = ImageDraw.Draw(im)
        d.text((width // 2, 28), title, font=bold, fill="#17365D", anchor="ma")
        return im, d

    def hbar(path, title, rows, color, max_value=None, value_format="{:.0f}"):
        im, d = canvas(title, 1500, max(620, 120 + 38 * len(rows)))
        left, right, top = 390, 1400, 95
        maximum = max_value or max(v for _, v in rows) * 1.08
        for i, (label, value) in enumerate(rows):
            y = top + i * 38
            d.text((left - 15, y + 12), label, font=tiny, fill="#222222", anchor="rm")
            x2 = left + int((right - left) * value / maximum)
            d.rectangle((left, y, x2, y + 24), fill=color)
            d.text((x2 + 8, y + 12), value_format.format(value), font=tiny, fill="#333333", anchor="lm")
        d.line((left, top - 8, left, top + len(rows) * 38), fill="#888888", width=2)
        im.save(path)

    hbar(ASSETS / "district_coverage.png", "Active attraction coverage by district", sorted(district_counts, key=lambda x: x[1], reverse=True), "#2F75B5")
    completeness_rows = [(k, 100 * a / b) for k, (a, b) in coverage.items()]
    hbar(ASSETS / "data_completeness.png", "Knowledge-base field completeness", completeness_rows, "#2F75B5", 105, "{:.1f}%")
    hbar(ASSETS / "category_distribution.png", "Category mapping distribution", category_counts, "#548235")
    hbar(ASSETS / "activity_distribution.png", "Top mapped activities", activity_counts, "#D9A441")

    def vbar(path, title, labels, series, maximum, colors, ylabel):
        im, d = canvas(title, 1500, 760)
        left, right, top, bottom = 125, 1420, 105, 620
        d.line((left, top, left, bottom), fill="#666666", width=2)
        d.line((left, bottom, right, bottom), fill="#666666", width=2)
        for step in range(6):
            value = maximum * step / 5
            y = bottom - int((bottom - top) * value / maximum)
            d.line((left, y, right, y), fill="#E5E5E5", width=1)
            d.text((left - 12, y), f"{value:.1f}", font=tiny, fill="#555555", anchor="rm")
        groups = len(labels)
        group_w = (right - left) / groups
        series_count = len(series)
        bar_w = min(115, int(group_w * .65 / series_count))
        for gi, label in enumerate(labels):
            center = left + group_w * (gi + .5)
            d.text((center, bottom + 20), label, font=tiny, fill="#333333", anchor="ma")
            for si, (sname, values) in enumerate(series):
                value = values[gi]
                x1 = int(center - series_count * bar_w / 2 + si * bar_w)
                x2 = x1 + bar_w - 8
                y1 = bottom - int((bottom - top) * value / maximum)
                d.rectangle((x1, y1, x2, bottom), fill=colors[si])
                d.text(((x1 + x2)//2, y1 - 8), f"{value:.3f}", font=tiny, fill="#333333", anchor="ms")
        d.text((35, (top+bottom)//2), ylabel, font=small, fill="#333333", anchor="mm")
        lx = left
        for si, (sname, _) in enumerate(series):
            d.rectangle((lx, 675, lx+24, 699), fill=colors[si])
            d.text((lx+32, 687), sname, font=tiny, fill="#333333", anchor="lm")
            lx += 180
        im.save(path)

    vbar(ASSETS / "weather_rain_metrics.png", "Daily Prophet rainfall-event classification", ["Accuracy", "Precision", "Recall", "F1"], [("Mean 2025 score", [0.6226, 0.8514, 0.5792, 0.6780])], 1.0, ["#2F75B5"], "Score")
    vbar(ASSETS / "weather_error_metrics.png", "Daily Prophet national 2025 test errors", ["Rainfall", "Min temp", "Max temp"], [("MAE", [5.5375, 0.9052, 1.3967]), ("RMSE", [13.7632, 1.0971, 1.6523])], 15.0, ["#2F75B5", "#D9A441"], "Error in target unit")
    vbar(ASSETS / "test_summary.png", "Verification executed on 27 October 2026", ["Recommend", "Weather", "Holiday+KB", "Climate+time", "Flutter"], [("Passed", [173, 213, 38, 268, 9]), ("Env failures", [0, 0, 0, 13, 0])], 300.0, ["#548235", "#C00000"], "Tests")

    im, d = canvas("Current Component 1 request and evidence flow", 1600, 760)
    boxes = [
        (40, 130, 280, 265, "User request\nFlutter UI"),
        (340, 130, 620, 265, "LangGraph\nparse - validate - clarify"),
        (680, 130, 940, 265, "BGE query vector\nQdrant top-K"),
        (1000, 130, 1325, 265, "PostgreSQL hydrate\nand hard filters"),
        (630, 390, 990, 555, "Four context adapters\nweather - time - holiday - seasonality"),
        (1060, 390, 1450, 555, "R0-R3 experimental rank\nexplanation - itinerary"),
    ]
    for x1, y1, x2, y2, label in boxes:
        d.rounded_rectangle((x1, y1, x2, y2), radius=12, fill="#DDEBF7", outline="#17365D", width=3)
        lines = label.split("\n")
        total_h = len(lines) * 28
        for j, line in enumerate(lines):
            d.text(((x1+x2)//2, (y1+y2)//2 - total_h//2 + j*30), line, font=small, fill="#17365D", anchor="ma")

    def arrow(a, b):
        d.line((a, b), fill="#17365D", width=4)
        x, y = b
        d.polygon([(x, y), (x-14, y-8), (x-14, y+8)], fill="#17365D")

    arrow((280, 198), (340, 198)); arrow((620, 198), (680, 198)); arrow((940, 198), (1000, 198))
    d.line((1160, 265, 1160, 330, 810, 330, 810, 390), fill="#17365D", width=4)
    d.polygon([(810,390),(802,376),(818,376)], fill="#17365D")
    arrow((990, 472), (1060, 472))
    d.text((50, 665), "External evidence: OpenWeatherMap, daily NASA POWER Prophet, historical climate, opening hours and holiday/event records", font=tiny, fill="#666666")
    im.save(ASSETS / "architecture.png")


def configure_doc(doc: Document):
    section = doc.sections[0]
    section.top_margin = Inches(.72)
    section.bottom_margin = Inches(.65)
    section.left_margin = Inches(.72)
    section.right_margin = Inches(.72)
    section.header_distance = Inches(.25)
    section.footer_distance = Inches(.25)

    styles = doc.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"]._element.rPr.rFonts.set(qn("w:ascii"), "Aptos")
    styles["Normal"]._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos")
    styles["Normal"].font.size = Pt(10.5)
    styles["Normal"].paragraph_format.space_after = Pt(6)
    styles["Normal"].paragraph_format.line_spacing = 1.12

    title = styles["Title"]
    title.font.name = "Aptos Display"
    title.font.size = Pt(25)
    title.font.bold = True
    title.font.color.rgb = RGBColor(0, 0, 0)
    title.paragraph_format.space_after = Pt(12)

    for name, size in (("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11)):
        style = styles[name]
        style.font.name = "Aptos Display"
        style._element.rPr.rFonts.set(qn("w:ascii"), "Aptos Display")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos Display")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(11)
        style.paragraph_format.space_after = Pt(5)

    header = section.header
    p = header.paragraphs[0]
    p.text = "SLIIT | BSc (Hons) Information Technology - Data Science | IT4010 Data Analysis Report"
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for r in p.runs:
        r.font.size = Pt(7.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor.from_string(NAVY)

    footer = section.footer
    p = footer.paragraphs[0]
    p.text = "WANDARAYA | Component 1 | J26-DS-337 | "
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for r in p.runs:
        r.font.size = Pt(7.5)
        r.font.color.rgb = RGBColor.from_string(GRAY)
    add_page_field(p)


def add_cover(doc):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(70)
    r = p.add_run("DATA ANALYSIS REPORT")
    r.bold = True
    r.font.size = Pt(28)
    r.font.color.rgb = RGBColor.from_string(NAVY)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Component 1 Project Coverage and Pending Work Audit")
    r.font.size = Pt(17)
    r.bold = True
    r.font.color.rgb = RGBColor.from_string(BLUE)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(20)
    p.add_run("Research Project IT4010\n").bold = True
    p.add_run("Project ID J26-DS-337\n")
    p.add_run("WANDARAYA Multi-Agentic AI for Sustainable Tourism in Sri Lanka\n")
    p.add_run("Individual component Context-Aware Recommendation Agent with Multi-Agent Orchestration")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(28)
    p.add_run("Student\n").bold = True
    p.add_run("IT23319738 | Mufeez M")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(28)
    p.add_run("Evidence cut-off 27 October 2026\n").bold = True
    p.add_run("Repository commit c35402ce642dfbcd9daed04bb2ac90f335ff27d2")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(55)
    r = p.add_run("Prepared from the current repository, live local services, model artifacts and executed tests. Previous-year material is used only for report structure.")
    r.font.size = Pt(9)
    r.italic = True
    r.font.color.rgb = RGBColor.from_string(GRAY)


def build_document():
    build_charts()
    doc = Document()
    configure_doc(doc)
    add_cover(doc)
    new_page(doc)

    doc.add_heading("Table of Contents", level=1)
    toc = [
        ("1", "Introduction and research scope"),
        ("2", "Data exploration"),
        ("3", "Methodology and implementation"),
        ("4", "Modelling and verified results"),
        ("5", "Proposal coverage and pending work"),
        ("6", "Completion roadmap"),
        ("7", "References and evidence register"),
        ("Appendix A", "Functional and non-functional requirement matrix"),
        ("Appendix B", "Verification record and submission checklist"),
    ]
    make_table(doc, ["Section", "Contents"], toc, widths=[1.25, 5.9])
    doc.add_heading("Executive conclusion", level=2)
    doc.add_paragraph(
        "Component 1 is a substantial working research prototype, not a finished production recommendation system. "
        "The knowledge base, semantic retrieval, four context adapters, experimental R0-R3 reranking, daily NASA POWER Prophet weather models, LangGraph orchestration and Flutter interface are implemented. "
        "The main scientific gap is independent relevance validation. The main functional gap is Group Emotion integration and user-feedback collection. The main operational gaps are taxonomy/enrichment completeness, production-grade latency, durable agent state, security hardening and verified cross-component integration."
    )
    make_table(doc, ["Evidence class", "Current result"], [
        ("Repository", "446 backend application Python files, 220 scripts, 23 migrations, 10 DAG files, 124 backend test files; 35 Flutter library files including 13 Component 1 files"),
        ("Runtime", "FastAPI, PostgreSQL, Redis, Qdrant, Airflow, MinIO and pgAdmin containers running; /health reports database, Redis and Qdrant OK"),
        ("Data", "6,120 active attractions; 6,120 configured staging vectors; 18 categories; 50 activities; active attractions in 21 of 25 district references"),
        ("Weather", "75 approved daily Prophet artifacts: 25 districts x rainfall/minimum/maximum temperature; 2010-2023 train, 2024 validation, 2025 test"),
        ("Executed verification", "692 targeted backend tests passed, 13 database-dependent climate tests blocked by Windows async PostgreSQL test configuration, and 9 selected Flutter tests passed"),
    ], widths=[1.25, 5.9])

    new_page(doc)
    add_section_title(doc, "1 Introduction and Research Scope")
    doc.add_heading("1.1 Background", level=2)
    doc.add_paragraph(
        "WANDARAYA Component 1 combines a Sri Lanka-specific tourism knowledge base with semantic retrieval and query-time context. Its research claim is not simply that relevant attractions can be found, but that ordering can respond to weather, time-of-day, Poya or event evidence, historical seasonality and later group emotion while retaining evidence and explanations."
    )
    doc.add_heading("1.2 Research problem", level=2)
    doc.add_paragraph(
        "Generic tourism search systems often emphasize keyword similarity or popularity. They may ignore whether a place is suitable for a requested date, hour, activity or Sri Lankan cultural context. Component 1 addresses this by separating semantic candidate retrieval from context-aware reranking and by preserving the original semantic order for safety and evaluation."
    )
    doc.add_heading("1.3 Scope of this report", level=2)
    add_bullets(doc, [
        "Audit the current backend, Flutter frontend, model artifacts, data services, APIs, tests and research reports against the proposal.",
        "Complete the Data Exploration, Methodology, Modelling and Results sections using current evidence.",
        "Identify implemented, experimental, pending and not-implemented work without treating code presence as scientific validation.",
        "Use the previous-year report only as a structural example; do not copy its train, hotel, immigration or multilingual results.",
    ])
    doc.add_heading("1.4 Evidence precedence", level=2)
    make_table(doc, ["Priority", "Evidence", "Use"], [
        ("1", "Current source code and configuration", "Defines implemented behavior and safety gates"),
        ("2", "Executed runtime queries and tests", "Confirms current services, counts and invariants"),
        ("3", "Current model/data artifacts", "Supplies reproducible metrics and provenance"),
        ("4", "Research documentation", "Explains design and historical experiments; checked for staleness"),
        ("5", "Proposal", "Defines intended objectives and requirements, not implementation proof"),
    ], widths=[.7, 2.45, 4.0])

    doc.add_heading("1.5 System architecture", level=2)
    add_picture(doc, ASSETS / "architecture.png", width=6.8)
    add_caption(doc, "Figure 1. Current Component 1 request and evidence flow")
    doc.add_paragraph(
        "The active flow is Flutter to FastAPI, then LangGraph intent handling, BGE/Qdrant semantic retrieval, PostgreSQL hydration, four context adapters, experimental reranking and explanation/itinerary composition. Group Emotion is not accepted by the unified-context schema. Production routing remains disabled even though the development research APIs are enabled."
    )

    new_page(doc)
    add_section_title(doc, "2 Data Exploration")
    doc.add_heading("2.1 Data collection and provenance", level=2)
    make_table(doc, ["Data domain", "Current source or store", "Purpose", "Verified status"], [
        ("Attractions", "Google Places plus curated/approved tourism sources in PostgreSQL/PostGIS", "Identity, coordinates, ratings, opening hours, categories and activities", "6,120 active records"),
        ("Descriptions", "Wikimedia/MediaWiki enrichment and source references", "Semantic text and user-facing descriptions", "51 active attractions have enrichment records; coverage is very low"),
        ("Semantic vectors", "BAAI/bge-large-en-v1.5 in Qdrant staging", "Meaning-based top-K retrieval", "6,120 points; 1,024 dimensions"),
        ("Daily climate", "NASA POWER processed files for 2010-2025", "Long-range date-specific statistical estimates", "25 districts, 5,844 days each, three targets"),
        ("Near-term weather", "OpenWeatherMap", "0-5 day forecast evidence", "Provider-dependent live request"),
        ("Time-of-day", "Stored opening hours in Asia/Colombo", "Open/closed and remaining-time suitability", "6,096 attractions contain opening-hours data"),
        ("Holiday and events", "Sri Lankan calendar and verified event records", "Poya, holiday, event date/location relevance", "Implemented but coverage and source governance remain incomplete"),
        ("Historical seasonality", "NASA POWER climatology plus attraction/activity mappings", "Month/activity suitability", "Implemented experimentally; mapping coverage varies by pilot"),
        ("Group emotion", "Planned Component 3 contract", "Fifth context dimension", "Deferred and not scored"),
    ], widths=[1.05, 2.2, 2.65, 1.3])

    doc.add_heading("2.2 Tourism knowledge-base description", level=2)
    doc.add_paragraph(
        "The runtime database has all 25 district reference rows, but active attractions are present in only 21 districts. Four districts - Kilinochchi, Mannar, Mullaitivu and Vavuniya - currently have zero active attractions. The earlier draft's statement that the attraction inventory spans all 25 districts is therefore not supported by the current database."
    )
    add_picture(doc, ASSETS / "district_coverage.png", width=6.8)
    add_caption(doc, "Figure 2. Active attraction count by district from the live PostgreSQL runtime")
    make_table(doc, ["Measure", "Verified value", "Interpretation"], [
        ("Active attractions", "6,120", "Current database inventory"),
        ("District reference rows", "25", "National administrative reference coverage"),
        ("Districts with active attractions", "21", "Four districts have no active attraction rows"),
        ("Category types", "18", "Tourism taxonomy"),
        ("Activity types", "50", "Activity taxonomy"),
        ("Duplicate Google place IDs", "0", "No duplicate non-null external IDs in the runtime query"),
    ], widths=[2.0, 1.25, 3.9])

    new_page(doc)
    doc.add_heading("2.3 Data completeness and imbalance", level=2)
    add_picture(doc, ASSETS / "data_completeness.png", width=6.6)
    add_caption(doc, "Figure 3. Field completeness among 6,120 active attractions")
    doc.add_paragraph(
        "Coordinates and external identity quality are strong. However, taxonomy and description evidence are not complete enough to support a claim that every attraction is richly represented. Missing activity mappings affect preference filtering, weather activity rules and seasonality linkage. Missing enrichment descriptions reduce explanation quality and can allow generic source text to dominate recommendations."
    )
    make_table(doc, ["Quality issue", "Count", "Share", "Research impact"], [
        ("Without category mapping", "1,115", "18.2%", "Category-focused retrieval and evaluation can omit or misclassify candidates"),
        ("Without activity mapping", "4,407", "72.0%", "Activity context, weather suitability and seasonality mapping are frequently unavailable"),
        ("Without enrichment description", "6,069", "99.2%", "Descriptions and semantic documents rely heavily on base/source fields"),
        ("Missing coordinates", "0", "0.0%", "Geographic filtering is available for active attractions"),
        ("Missing opening hours", "24", "0.4%", "Small but important uncertainty for itinerary scheduling"),
        ("Missing ratings", "1,142", "18.7%", "Popularity/rating evidence cannot be used consistently"),
    ], widths=[1.75, .7, .7, 4.0])

    doc.add_heading("2.4 Category and activity distributions", level=2)
    add_picture(doc, ASSETS / "category_distribution.png", width=6.35)
    add_caption(doc, "Figure 4. Category mappings are multi-label and therefore do not sum to the attraction count")
    add_picture(doc, ASSETS / "activity_distribution.png", width=6.35)
    add_caption(doc, "Figure 5. Top fifteen activity mappings; the long tail and unmapped records require separate analysis")

    new_page(doc)
    doc.add_heading("2.5 Daily NASA POWER dataset", level=2)
    doc.add_paragraph(
        "The current daily weather pipeline supersedes the older monthly-only description. Each district file contains daily NASA POWER observations from 1 January 2010 through 31 December 2025. The loader validates dates, duplicates, provider sentinel values, physical ranges and minimum/maximum temperature order. Missing dates are explicitly reindexed rather than silently ignored. NASA POWER represents a coarse district-level grid sample, so the result is not attraction-level weather truth."
    )
    make_table(doc, ["Element", "Implementation"], [
        ("Targets", "Daily rainfall, minimum temperature and maximum temperature"),
        ("Coverage", "25 district identifiers, 5,844 calendar days per source file"),
        ("Train split", "2010-01-01 to 2023-12-31"),
        ("Validation split", "2024-01-01 to 2024-12-31; rainfall decision threshold selected only here"),
        ("Test split", "2025-01-01 to 2025-12-31; held out from threshold selection"),
        ("Final fit", "2010-01-01 to 2025-12-31 after evaluation"),
        ("Artifacts", "75 model.json plus 75 manifest.json files with SHA-256 verification"),
        ("Forecast window", "Dates after 2025-12-31; 0-5 day requests still prefer the live provider"),
    ], widths=[1.55, 5.6])
    doc.add_paragraph(
        "Rainfall is log1p-transformed during fitting and converted back after prediction. The operational rain/no-rain decision does not assume that any small non-zero estimate is a rainy day. Observed rain is defined at 0.5 mm, while each district uses a validation-selected prediction threshold. For Galle the threshold is 3.524473 mm/day."
    )

    doc.add_heading("2.6 Suitability to research objectives", level=2)
    make_table(doc, ["Dataset", "SO1", "SO2", "SO3", "SO4", "SO5", "SO6"], [
        ("Attraction KB", "Yes", "Yes", "Yes", "Yes", "Yes", "Yes"),
        ("BGE/Qdrant vectors", "Yes", "Yes", "Yes", "Yes", "Yes", "Yes"),
        ("Daily/live weather", "-", "-", "Yes", "Yes", "Yes", "Yes"),
        ("Opening hours", "Yes", "-", "Yes", "Yes", "Yes", "Yes"),
        ("Holiday/event", "-", "-", "Yes", "Yes", "Yes", "Yes"),
        ("Seasonality", "-", "-", "Yes", "Yes", "Yes", "Yes"),
        ("Group emotion", "-", "-", "Pending", "Pending", "Pending", "Pending"),
        ("Human relevance/SUS", "-", "Pending", "Pending", "Pending", "-", "Pending"),
    ], widths=[2.0, .7, .7, .7, .7, .7, .7])

    new_page(doc)
    add_section_title(doc, "3 Methodology and Implementation")
    doc.add_heading("3.1 Research and development method", level=2)
    doc.add_paragraph(
        "The proposal uses Design Science Research with quantitative comparative evaluation and Agile iterative implementation. The artifact-development stages are visible in the repository as separate knowledge-base, retrieval, context, evaluation, graph and frontend modules. Scientific completion, however, requires more than implementation: the planned independent relevance and user evaluations remain unfinished."
    )
    make_table(doc, ["Iteration", "Current evidence", "Status"], [
        ("1 Research and requirements", "Proposal, architecture, metrics and source-governance documents", "COMPLETE"),
        ("2 Tourism knowledge base", "PostgreSQL/PostGIS schema, ingestion pipelines, 6,120 records and 6,120 vectors", "PARTIAL"),
        ("3 Baseline recommendation", "Deterministic content baseline and R0 semantic baseline", "PARTIAL"),
        ("4 Semantic candidate retrieval", "BGE/Qdrant/PostgreSQL retrieval path", "IMPLEMENTED"),
        ("5 Context re-ranking", "Four adapters plus R0-R3 experimental ranker", "PARTIAL"),
        ("6 Experimental evaluation", "Infrastructure and exploratory results; independent labels incomplete", "PARTIAL"),
        ("7 Multi-agent integration", "LangGraph research workflow", "PARTIAL"),
        ("8 User evaluation", "No completed SUS or recommendation relevance study", "NOT IMPLEMENTED"),
        ("9 Optimization/documentation", "Extensive docs; production validation and optimization pending", "PARTIAL"),
    ], widths=[1.8, 4.45, 1.15], status_col=2)

    doc.add_heading("3.2 Data preprocessing", level=2)
    make_table(doc, ["Pipeline", "Cleaning and transformation", "Validation"], [
        ("Attractions", "Normalize names/text/URLs, preserve canonical IDs, map district/category/activity, de-duplicate external IDs", "Coordinates, active state, provenance and duplicate checks"),
        ("Descriptions", "Remove boilerplate and normalize whitespace before composing semantic documents", "Source references and timestamped enrichment"),
        ("Embeddings", "Build one consistent searchable document and L2-normalize BGE vectors", "Require exactly 1,024 dimensions and canonical attraction IDs"),
        ("Daily climate", "Parse daily dates/numerics, replace impossible values, reindex missing dates, log-transform rainfall", "Non-overlapping train/validation/test periods and artifact checksums"),
        ("Opening hours", "Parse schedules in Asia/Colombo and preserve unknown status", "Unknown is not treated as closed; verified closed is a hard operational restriction"),
        ("Holiday/events", "Normalize local dates, locations and event categories", "No venue restriction is inferred without evidence"),
        ("Ranking traces", "Preserve query, candidate, semantic rank, experimental rank and contribution evidence", "Production order must remain unchanged in research mode"),
    ], widths=[1.25, 3.65, 2.5])

    new_page(doc)
    doc.add_heading("3.3 Feature extraction and models", level=2)
    make_table(doc, ["Layer", "Features or model", "Output"], [
        ("Semantic", "1,024-D BGE vector, raw cosine-like score, shifted normalized score, category/activity/geography matches", "Top-K candidate IDs, evidence and baseline score"),
        ("Weather", "Forecast rainfall, rain probability where available, min/max temperature, activity thresholds, provenance and uncertainty", "Suitability 0-1 or null; source-specific confidence"),
        ("Time", "Visit time, opening window, closing horizon and unknown status", "Open/partial/closed suitability; closed may hard-zero experimental score"),
        ("Holiday/event", "Date, event type, location and interest relevance", "Evidence score or explicit unavailable state"),
        ("Seasonality", "District-month climate, activity mapping and profile weights", "Historical suitability with mapping/proxy provenance"),
        ("Group emotion", "Contract only", "Not accepted or scored in the current engine"),
        ("Unified ranker", "R0 semantic; R1 equal available context; R2 confidence-weighted; R3 weather-seasonality combination", "Final experimental score, rank movement and explanation"),
        ("Agent", "Deterministic intent/date parsing, clarification, destination/activity resolution and result verification", "Recommendations, itinerary, not-recommended alternatives and diagnostics"),
    ], widths=[1.15, 4.4, 1.85])

    doc.add_heading("3.4 Ranking formula and missing evidence", level=2)
    doc.add_paragraph(
        "For R1-R3, the implementation uses final_score = alpha x normalized_semantic_score + (1 - alpha) x context_score, with alpha normally 0.65. Context score is computed only from eligible available dimensions. Missing evidence is excluded and the remaining weights are renormalized. This is preferable to assigning zero, because zero would incorrectly mean verified unsuitability. R3 first combines weather and historical seasonality to reduce double counting."
    )
    doc.add_paragraph(
        "An attraction that explicitly matches the requested interest remains ahead of unrelated candidates before final score sorting. A verified closed status is a hard operational restriction for contextual configurations. These safeguards explain why the experimental ranker is not simply a weighted sum over every field."
    )

    doc.add_heading("3.5 Weather source routing", level=2)
    make_table(doc, ["Requested date", "Selected evidence", "Meaning"], [
        ("Past", "Historical observations", "Observed evidence, not forecast"),
        ("Today through 5 days", "OpenWeatherMap", "Near-term provider forecast"),
        ("More than 5 days", "Daily NASA POWER Prophet", "Date-specific long-range statistical estimate"),
    ], widths=[1.6, 2.2, 3.6])
    doc.add_paragraph(
        "The daily model is now integrated through WeatherContextService and WeatherAdapter. This corrects the third PDF's older statement that Prophet was merely a candidate extension. Nevertheless, the daily output must be described as an estimate with an 80% interval, not an exact prediction or safety guarantee."
    )

    add_section_title(doc, "4 Modelling and Verified Results")
    doc.add_heading("4.1 Semantic representation and runtime retrieval", level=2)
    doc.add_paragraph(
        "The configured embedding model is BAAI/bge-large-en-v1.5. It generates normalized 1,024-dimensional document and query vectors. Qdrant returns point IDs and similarity scores; PostgreSQL then hydrates only active attraction rows. The API status reports 6,120 active attractions and 6,120 points in the configured staging collection. Vector dimension and point-count parity validate synchronization, not retrieval relevance."
    )
    doc.add_paragraph(
        "A separate direct request to the default local Qdrant collection returned a dirty-shard initialization error while the API-configured staging collection remained available. The deployment therefore needs a documented collection cutover, alias and recovery procedure before production."
    )

    doc.add_heading("4.2 Daily Prophet configuration", level=2)
    make_table(doc, ["Parameter", "Value"], [
        ("Growth", "Linear"),
        ("Yearly seasonality", "Fourier order 10"),
        ("Weekly seasonality", "Disabled"),
        ("Daily seasonality", "Disabled because there is one observation per day"),
        ("Seasonality mode", "Additive"),
        ("Changepoint prior scale", "0.03"),
        ("Seasonality prior scale", "5.0"),
        ("Prediction interval", "80%"),
        ("Minimum data", "At least three years of unique daily observations"),
        ("Rain transformation", "log1p for fit; expm1 and clip at zero for output"),
    ], widths=[2.2, 4.95])

    doc.add_heading("4.3 National weather evaluation", level=2)
    add_picture(doc, ASSETS / "weather_error_metrics.png", width=6.45)
    add_caption(doc, "Figure 6. Mean 2025 held-out test error across 25 districts; target units differ")
    add_picture(doc, ASSETS / "weather_rain_metrics.png", width=6.25)
    add_caption(doc, "Figure 7. Mean rainfall-event metrics using validation-selected district thresholds")
    doc.add_paragraph(
        "Across 25 districts, rainfall-event precision is high (0.851 mean) but recall is lower (0.579 mean), showing that the model is conservative and misses some rainy days. The mean rainfall bias is -3.233 mm/day, indicating underprediction. Temperature estimates are more stable: mean 2025 MAE is 0.905 C for minimum temperature and 1.397 C for maximum temperature, although both show positive bias."
    )

    new_page(doc)
    doc.add_heading("4.4 Galle model example", level=2)
    make_table(doc, ["Target", "2025 test result", "Interpretation"], [
        ("Rainfall", "MAE 6.736 mm/day; RMSE 15.473; precision 0.935; recall 0.623; F1 0.748", "Strong precision but substantial amount error and missed rain events"),
        ("Minimum temperature", "MAE 0.696 C; RMSE 0.823; bias +0.685 C", "Moderate accuracy with warm bias"),
        ("Maximum temperature", "MAE 0.855 C; RMSE 0.993; bias +0.830 C", "Moderate accuracy with warm bias"),
    ], widths=[1.3, 3.3, 2.55])
    doc.add_paragraph(
        "For 15 November 2026, the verified Galle artifacts returned 8.90 mm/day rainfall with an 80% interval of 2.08-30.15 mm/day, 26.98 C minimum temperature and 28.64 C maximum temperature. Because 8.90 exceeds Galle's validation-selected 3.524473 mm/day prediction threshold, rain_expected is true. This is a reproducible model demonstration, not a statement of what the weather will certainly be."
    )

    doc.add_heading("4.5 Seasonality evaluation", level=2)
    doc.add_paragraph(
        "The Stage 12.4F inspected benchmark contains 52 complete attraction-activity month-ranking queries. The district multivariable reference achieved mean NDCG@5 0.9157; the fixed retrospective blend achieved 0.9161; the activity-aware candidate achieved 0.8971. These values are exploratory because the benchmark is small and cluster-dependent. No refined seasonality candidate is production-approved."
    )
    make_table(doc, ["Candidate", "Mean NDCG@5", "Decision"], [
        ("Activity-aware", "0.8971", "Did not outperform district reference"),
        ("District multivariable reference", "0.9157", "Retained as best-supported reference"),
        ("Fixed calibrated blend", "0.9161", "Difference too small and not independently confirmed"),
        ("Grouped-CV blend", "0.9140", "Exploratory; not approved"),
    ], widths=[2.5, 1.25, 3.4])
    doc.add_paragraph(
        "Two historical pilots report different seasonality coverage: Stage 12.4G recorded 10/15 candidates, mostly district proxies, while the later Stage 12.5 unified pilot recorded 0/15 genuine attraction/activity seasonality mappings. These are not interchangeable samples. The current report preserves both findings and treats genuine mapping coverage as unresolved until a new controlled run is executed."
    )

    doc.add_heading("4.6 Context and LangGraph pilots", level=2)
    make_table(doc, ["Pilot", "Observed result", "What it proves", "What it does not prove"], [
        ("Stage 12.5 unified context", "3 requests, 15 returned candidates, no adapter errors; warm average about 714 ms; cold about 18.8 s", "Functional evidence flow and deterministic behavior", "Relevance, production latency or user satisfaction"),
        ("Stage 12.6 LangGraph", "3/3 requests completed; 15 candidates; cold 39.8 s; warm 4.7 s and 0.75 s", "Graph routing, clarification and composition", "Statistical reliability or <=2 s performance"),
        ("Current API", "Development research APIs enabled; production routing flags false", "Safe experimental access", "Production readiness"),
    ], widths=[1.4, 2.6, 1.7, 1.7])

    new_page(doc)
    doc.add_heading("4.7 Current test verification", level=2)
    add_picture(doc, ASSETS / "test_summary.png", width=6.6)
    add_caption(doc, "Figure 8. Tests executed for this report; categories are separate commands")
    make_table(doc, ["Test scope", "Passed", "Failed", "Interpretation"], [
        ("Recommendation and LangGraph", "173", "0", "Current recommendation, schema, security and graph behavior passed"),
        ("Weather model", "213", "0", "Daily/monthly model, registry, suitability and integrity tests passed"),
        ("Holiday and knowledge base", "38", "0", "Parser, mapping and knowledge connector tests passed"),
        ("Climate and time", "268", "13", "Most passed; failures require async PostgreSQL/Docker test configuration on Windows"),
        ("Selected Flutter Component 1", "9", "0", "Models, UI states and responsive screens passed"),
    ], widths=[2.2, .75, .75, 3.3])
    doc.add_paragraph(
        "The 13 failures are all from database-dependent climate persistence tests that attempted psycopg async connections with the Windows Proactor event loop and Docker hostname. They must be rerun inside the Linux API/test container or with WindowsSelectorEventLoopPolicy and an accessible database URL. They are recorded as unverified integration evidence, not recommendation-model failures."
    )

    doc.add_heading("4.8 Claims that must not be made yet", level=2)
    add_bullets(doc, [
        "Do not call 6,120 records a nationally balanced attraction dataset; four districts have no active records and several districts have fewer than ten.",
        "Do not infer retrieval quality from a 1,024-dimensional embedding or matching point count.",
        "Do not call tests or three-request pilots recommendation accuracy.",
        "Do not present daily Prophet output as an exact daily weather forecast or attraction-level meteorology.",
        "Do not claim all five context dimensions are integrated; Group Emotion is deferred.",
        "Do not claim the <=2 second requirement is met until cold/warm p50, p95 and p99 load tests pass.",
        "Do not call research reranking production behavior; the implementation intentionally preserves production order.",
    ])

    new_page(doc)
    add_section_title(doc, "5 Proposal Coverage and Pending Work")
    doc.add_heading("5.1 Specific-objective coverage", level=2)
    make_table(doc, ["ID", "Objective", "Status", "Current evidence", "Pending work"], objective_rows, widths=[.45, 1.35, .85, 2.35, 2.4], status_col=2)

    doc.add_heading("5.2 User-requirement coverage", level=2)
    make_table(doc, ["ID", "Requirement", "Status and evidence"], [
        ("UR1", "Personalized recommendations", "Implemented experimentally through interests, activity, category, geography and semantic relevance"),
        ("UR2", "Context-aware recommendations", "Partial: four contexts work; Group Emotion does not"),
        ("UR3", "Semantic discovery", "Implemented with BGE/Qdrant"),
        ("UR4", "Sri Lanka-specific information", "Implemented with material coverage gaps across districts, activities and enrichment"),
        ("UR5", "Ranked recommendations", "Implemented experimentally; production ranking remains protected"),
        ("UR6", "Understandable explanation", "Implemented with evidence, provenance, limitations and reason text"),
        ("UR7", "Group-level emotion or vibe", "Not integrated into Component 1"),
        ("UR8", "Responsive interaction", "Not yet demonstrated for all paths; cold starts exceed target"),
    ], widths=[.55, 2.55, 4.55])

    doc.add_heading("5.3 Main document-to-project mismatches", level=2)
    make_table(doc, ["Document statement", "Current project evidence", "Required correction"], [
        ("Attraction inventory spans all 25 districts", "25 reference districts but active attractions in 21", "Report both values and name zero-coverage districts"),
        ("Prophet is only a candidate monthly extension", "Daily Prophet is trained, approved and integrated for all 25 districts", "Replace with daily data, splits, artifacts and test metrics"),
        ("Four context layers are operational with one fixed coverage result", "Coverage differs by pilot and configuration", "Cite pilot version and distinguish genuine mapping from district proxy"),
        ("Group Emotion is the fifth active context", "Schema rejects it and flags are false", "Describe contract-ready future integration"),
        ("Production system is complete", "Research APIs are enabled in development while production routing is false", "Use experimental/prototype wording"),
        ("Description-rich recommendations", "Only 51 active attractions have enrichment descriptions", "Prioritize verified descriptions and report coverage"),
    ], widths=[2.25, 2.7, 2.2])

    add_section_title(doc, "6 Completion Roadmap")
    doc.add_heading("6.1 Priority sequence", level=2)
    make_table(doc, ["Priority", "Work package", "Definition of done"], [
        ("P0", "Freeze reproducible audit baseline", "Commit or stash the two current modified files; record commit, environment, collection alias and dataset/model checksums"),
        ("P0", "Repair Qdrant deployment state", "One approved collection/alias, no dirty shards, matching 6,120 IDs, tested snapshot restore and documented cutover"),
        ("P0", "Complete KB quality repair", "All 25 districts represented or exclusions justified; category/activity/description coverage targets defined and audited"),
        ("P0", "Independent retrieval relevance set", "Frozen queries, blinded labels, reviewer agreement and lexical/semantic baseline comparison with Precision, Recall, NDCG and MRR"),
        ("P1", "Unified context experiment", "Same candidates and judgments across R0-R3, with per-query effects, evidence coverage, confidence intervals and failure analysis"),
        ("P1", "Group Emotion R4 integration", "Component 3 contract, consent/privacy, attraction mapping, unavailable behavior, ablation and independent validation"),
        ("P1", "Performance and resilience", "Cold/warm p50/p95/p99, concurrent load, provider timeout, database/Qdrant failure and fallback tests"),
        ("P1", "Mobile feedback and usability", "Feedback API/storage, task scripts, real participants, SUS scoring and recommendation usefulness analysis"),
        ("P2", "Security hardening", "Scoped authentication, no local bypass in deployment, CORS allowlist, rate limits, secrets review and audit logging"),
        ("P2", "Cross-component integration", "Versioned REST/JSON contracts and end-to-end tests with Components 2, 3 and 4"),
        ("P2", "Production trial", "Only after scientific, data, reliability and security gates pass; reversible rollout and monitoring"),
    ], widths=[.55, 2.15, 4.6])

    doc.add_heading("6.2 Recommended experiments", level=2)
    add_bullets(doc, [
        "Retrieval: popularity baseline, lexical TF-IDF/content baseline, semantic R0 and human-labeled relevance at fixed K.",
        "Context ablation: R0 semantic; +weather; +time; +holiday/event; +seasonality; later +group emotion, with the same candidate pools and judgments.",
        "Weather: rolling-origin district evaluation, rain-event calibration curves, comparison against seasonal naive and climatology, and attraction-distance sensitivity.",
        "Data quality: district/category/activity missingness before and after repair, duplicate/identity checks and description-source audits.",
        "Agent: clarification completion, destination-resolution errors, provider timeouts, durable checkpoint restart and cross-session ownership tests.",
        "Frontend: task completion, accessibility, comprehension of uncertainty, usefulness ratings and SUS with real participants.",
    ])

    doc.add_heading("6.3 Immediate submission checklist", level=2)
    make_table(doc, ["Item", "Current state", "Action before submission"], [
        ("Project identity and scope", "Complete", "Confirm supervisor-approved title and project ID"),
        ("Actual dataset counts", "Current runtime captured", "Export dated CSV/SQL evidence and commit it"),
        ("EDA figures", "Included from current runtime", "Recreate automatically from frozen exports for reproducibility"),
        ("Daily weather evaluation", "Included", "Add per-district appendix and baseline comparison"),
        ("Retrieval metrics", "Pending", "Collect labels and execute baseline evaluation"),
        ("Five-context experiment", "Pending", "Do not claim completion until Group Emotion and ablation are validated"),
        ("User/SUS results", "Pending", "Obtain ethics/consent as required, run study and report sample size"),
        ("References", "Technical sources listed", "Verify access dates, dataset licenses and IEEE bibliographic metadata"),
        ("Reproducibility", "Partial", "Freeze commit, environment, collection alias, data/model checksums and run commands"),
    ], widths=[2.0, 1.8, 3.5])

    new_page(doc)
    add_section_title(doc, "7 References and Evidence Register")
    references = [
        "[1] M. Mufeez, Component 1 research proposal, IT23319738, 15 September 2026.",
        "[2] WANDARAYA repository, commit c35402ce642dfbcd9daed04bb2ac90f335ff27d2, inspected 27 October 2026.",
        "[3] Sri Lanka Tourism Development Authority, Tourist Attractions, https://www.sltda.gov.lk/en/tourist-attractions.",
        "[4] Google, Places API documentation, https://developers.google.com/maps/documentation/places/web-service.",
        "[5] NASA, POWER Data Access Viewer and API, https://power.larc.nasa.gov/.",
        "[6] OpenWeather, Weather API documentation, https://openweathermap.org/api.",
        "[7] Beijing Academy of Artificial Intelligence, BAAI/bge-large-en-v1.5 model card, https://huggingface.co/BAAI/bge-large-en-v1.5.",
        "[8] Qdrant, Documentation, https://qdrant.tech/documentation/.",
        "[9] LangChain, LangGraph documentation, https://docs.langchain.com/oss/python/langgraph/overview.",
        "[10] Meta Open Source, Prophet documentation, https://facebook.github.io/prophet/.",
        "[11] PostgreSQL Global Development Group, Documentation, https://www.postgresql.org/docs/.",
        "[12] PostGIS Project, Documentation, https://postgis.net/documentation/.",
        "[13] Internal model report, data/weather/modeling/nasa_power/reports/daily_prophet_evaluation.csv.",
        "[14] Internal model manifests, data/weather/artifacts/daily_nasa_prophet/district_*/{target}/manifest.json.",
        "[15] Internal research reports, docs/research/STAGE_12_4F_MODEL_COMPARISON.md, STAGE_12_5_SHADOW_PILOT_RESULTS.md and STAGE_12_6_TEST_RESULTS.md.",
    ]
    for ref in references:
        p = doc.add_paragraph(ref)
        p.paragraph_format.left_indent = Inches(.2)
        p.paragraph_format.first_line_indent = Inches(-.2)
        p.paragraph_format.space_after = Pt(5)

    doc.add_heading("7.1 Repository evidence locations", level=2)
    make_table(doc, ["Capability", "Primary evidence path"], [
        ("Embedding and retrieval", "app/knowledge_base/embeddings and app/knowledge_base/retrieval"),
        ("Content baseline", "app/recommendation/content_based"),
        ("Unified context", "app/recommendation/unified_context"),
        ("Daily weather", "app/weather_model/datasets/nasa_power_daily.py; forecasting/daily_prophet.py; context/daily_forecast_provider.py"),
        ("Seasonality", "app/climate and docs/research/STAGE_12_4*"),
        ("Holiday/event", "app/holiday_event and config/holiday_event_scoring.yaml"),
        ("LangGraph", "app/agents/recommendation_graph"),
        ("FastAPI contracts", "app/routers and live /openapi.json"),
        ("Flutter Component 1", "wandaraya_frontend/lib/features/component1"),
        ("Tests", "wandaraya-backend/tests and wandaraya_frontend/test"),
    ], widths=[2.0, 5.15])

    new_page(doc)
    add_section_title(doc, "Appendix A Functional and Non-Functional Requirement Matrix")
    doc.add_heading("A.1 Functional requirements", level=2)
    make_table(doc, ["ID", "Requirement", "Status", "Evidence or gap"], fr_rows, widths=[.45, 2.1, 1.0, 4.0], status_col=2)
    doc.add_heading("A.2 Non-functional requirements", level=2)
    make_table(doc, ["ID", "Requirement", "Status", "Evidence or gap"], nfr_rows, widths=[.55, 1.75, 1.05, 4.2], status_col=2)

    add_section_title(doc, "Appendix B Verification Record and Submission Notes")
    doc.add_heading("B.1 Commands and observations", level=2)
    make_table(doc, ["Check", "Observed result"], [
        ("Docker services", "API, PostgreSQL, Qdrant, Airflow, Redis, MinIO and pgAdmin running"),
        ("FastAPI health", "status ok; db ok; redis ok; qdrant ok"),
        ("Knowledge-base status", "6,120 active and mapped attractions; 18 categories; 50 activities; 6,120 staging Qdrant points"),
        ("Knowledge-base quality", "0 missing coordinates; 1,115 without category; 4,407 without activity; 6,069 without enrichment; 0 duplicate place IDs"),
        ("OpenAPI", "34 paths"),
        ("Daily models", "25 district folders, 75 model files and 75 manifests"),
        ("Backend tests", "692 passed; 13 environment-dependent climate persistence failures"),
        ("Flutter tests", "9 passed"),
        ("Working tree", "Two modified files at audit time: recommendation_graph/nodes/handlers.py and test_weather_alternatives.py"),
    ], widths=[2.15, 5.0])

    doc.add_heading("B.2 Interpretation of the supplied files", level=2)
    make_table(doc, ["Supplied file", "Use in this report"], [
        ("IT23319738.pdf", "Primary source for proposal objectives, methodology, requirements and intended architecture"),
        ("Data Analysis Report - -Bs9I2im3.pdf", "Previous-year structural example only; its datasets and results are not reused as Component 1 evidence"),
        ("WANDARAYA_Component1_Detailed_Data_Exploration_to_References.pdf", "Earlier 10-page draft; corrected and expanded by this report"),
        ("referalissa.docx", "Not used: it contains unrelated computer-security lecture notes, not Component 1 references"),
    ], widths=[2.75, 4.4])
    doc.add_paragraph(
        "Final assessment: the implementation is broad and technically substantial, but the dissertation should present it as an experimental research prototype. The decisive remaining work is independent evaluation, not the addition of more unvalidated features."
    )

    doc.save(DOCX_PATH)
    print(DOCX_PATH)


if __name__ == "__main__":
    build_document()
