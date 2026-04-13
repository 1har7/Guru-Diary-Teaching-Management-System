import io
import zipfile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
PERIOD_LABELS = [
    (1, "1st (9:50-10:50)"),
    (2, "2nd (10:50-11:50)"),
    (3, "3rd (12:00-1:00)"),
    (4, "4th (1:00-2:00)"),
    (5, "5th (2:30-3:30)"),
    (6, "6th (3:30-4:30)"),
]


def _make_grid_table(grid_data, cell_fmt):
    header = ["Period"] + [d[:3] for d in DAYS]
    rows = [header]
    for period, label in PERIOD_LABELS:
        row = [label]
        for day in DAYS:
            key = (day, period)
            val = grid_data.get(key)
            row.append(cell_fmt(val) if val else "—")
        rows.append(row)
    return rows


def pdf_lecturer_wise(slot_rows):
    """
    slot_rows: list of dicts with keys:
      day, period, lecturer, subject_code, subject_name, class_name
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(name="Title", parent=styles["Heading1"], fontSize=14, spaceAfter=12)

    by_lecturer = {}
    for s in slot_rows:
        day = s.get("day")
        period = s.get("period")
        lecturer = s.get("lecturer") or ""
        if not day or not period or not lecturer:
            continue
        key = (day, int(period))
        by_lecturer.setdefault(lecturer, {})[key] = (
            s.get("subject_code", "") or "",
            s.get("subject_name", "") or "",
            s.get("class_name", "") or "",
        )

    if not by_lecturer:
        doc.build([Paragraph("No timetable data.", title_style)])
        return buf.getvalue()

    story = []
    lecturer_list = sorted(by_lecturer.keys())
    for i, lecturer in enumerate(lecturer_list):
        grid = by_lecturer[lecturer]

        def fmt(val):
            code, name, cls = val
            return f"{code} {name} - {cls}".strip() or "-"

        table_data = _make_grid_table(grid, fmt)
        t = Table(table_data, colWidths=[1.2 * inch] + [0.9 * inch] * 6)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        story.append(Paragraph("Lecturer: " + lecturer, title_style))
        story.append(t)
        story.append(Spacer(1, 0.3 * inch))
        if i < len(lecturer_list) - 1:
            story.append(PageBreak())

    doc.build(story)
    return buf.getvalue()


def pdf_class_wise(slot_rows):
    """
    slot_rows: list of dicts with keys:
      day, period, lecturer, subject_code, subject_name, class_name
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(name="Title", parent=styles["Heading1"], fontSize=14, spaceAfter=12)

    by_class = {}
    for s in slot_rows:
        day = s.get("day")
        period = s.get("period")
        class_name = s.get("class_name") or ""
        if not day or not period or not class_name:
            continue
        key = (day, int(period))
        by_class.setdefault(class_name, {})[key] = (
            s.get("subject_code", "") or "",
            s.get("subject_name", "") or "",
            s.get("lecturer", "") or "",
        )

    if not by_class:
        doc.build([Paragraph("No timetable data.", title_style)])
        return buf.getvalue()

    story = []
    class_list = sorted(by_class.keys())
    for i, class_name in enumerate(class_list):
        grid = by_class[class_name]

        def fmt(val):
            code, name, lec = val
            return f"{code} {name} - {lec}".strip() or "-"

        table_data = _make_grid_table(grid, fmt)
        t = Table(table_data, colWidths=[1.2 * inch] + [0.9 * inch] * 6)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        story.append(Paragraph("Class: " + class_name, title_style))
        story.append(t)
        story.append(Spacer(1, 0.3 * inch))
        if i < len(class_list) - 1:
            story.append(PageBreak())

    doc.build(story)
    return buf.getvalue()


def zip_timetable_pdfs(slot_rows, *, zip_name="guru_diary_timetables.zip"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("timetable_lecturers.pdf", pdf_lecturer_wise(slot_rows))
        zf.writestr("timetable_classes.pdf", pdf_class_wise(slot_rows))
    return zip_name, buf.getvalue()

