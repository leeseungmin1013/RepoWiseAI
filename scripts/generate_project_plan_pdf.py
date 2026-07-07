from __future__ import annotations

import re
import sys
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "PROJECT_PLAN.md"
OUTPUT = ROOT / "output" / "pdf" / "RepoWiseAI_Project_Plan.pdf"
TMP_DIR = ROOT / "tmp" / "pdfs"

FONT_REGULAR = "MalgunGothic"
FONT_BOLD = "MalgunGothic-Bold"
FONT_REGULAR_PATH = Path(r"C:\Windows\Fonts\malgun.ttf")
FONT_BOLD_PATH = Path(r"C:\Windows\Fonts\malgunbd.ttf")


def register_fonts() -> None:
    if not FONT_REGULAR_PATH.exists() or not FONT_BOLD_PATH.exists():
        raise FileNotFoundError("Malgun Gothic fonts were not found in C:\\Windows\\Fonts")

    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(FONT_REGULAR_PATH)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_BOLD_PATH)))


def styles() -> dict[str, ParagraphStyle]:
    base = {
        "fontName": FONT_REGULAR,
        "fontSize": 10.2,
        "leading": 16,
        "textColor": colors.HexColor("#1f2937"),
        "wordWrap": "CJK",
        "alignment": TA_LEFT,
        "spaceAfter": 5,
    }

    def make_style(name: str, **overrides) -> ParagraphStyle:
        data = base.copy()
        data.update(overrides)
        return ParagraphStyle(name, **data)

    return {
        "title": make_style(
            "title",
            fontName=FONT_BOLD,
            fontSize=22,
            leading=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
            spaceAfter=14,
        ),
        "subtitle": make_style(
            "subtitle",
            fontSize=11,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#4b5563"),
            spaceAfter=6,
        ),
        "h2": make_style(
            "h2",
            fontName=FONT_BOLD,
            fontSize=15,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "h3": make_style(
            "h3",
            fontName=FONT_BOLD,
            fontSize=12.4,
            leading=18,
            textColor=colors.HexColor("#1e3a8a"),
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "h4": make_style(
            "h4",
            fontName=FONT_BOLD,
            fontSize=11.2,
            leading=17,
            textColor=colors.HexColor("#334155"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "body": make_style("body"),
        "bullet": make_style(
            "bullet",
            leftIndent=15,
            firstLineIndent=-9,
            bulletIndent=4,
            spaceAfter=3,
        ),
        "number": make_style(
            "number",
            leftIndent=17,
            firstLineIndent=-12,
            bulletIndent=2,
            spaceAfter=3,
        ),
        "table": make_style(
            "table",
            fontSize=8.6,
            leading=12.4,
            spaceAfter=0,
        ),
        "table_header": make_style(
            "table_header",
            fontName=FONT_BOLD,
            fontSize=8.8,
            leading=12.5,
            textColor=colors.HexColor("#111827"),
            spaceAfter=0,
        ),
        "code": ParagraphStyle(
            "code",
            fontName=FONT_REGULAR,
            fontSize=8.1,
            leading=11.2,
            textColor=colors.HexColor("#111827"),
            wordWrap="CJK",
        ),
    }


def inline_markdown(text: str) -> str:
    text = escape(text)
    text = text.replace("  ", " &nbsp;")

    def replace_code(match: re.Match[str]) -> str:
        return (
            '<font face="MalgunGothic-Bold" color="#0f766e">'
            + match.group(1)
            + "</font>"
        )

    text = re.sub(r"`([^`]+)`", replace_code, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def column_widths(col_count: int, available_width: float) -> list[float]:
    if col_count == 2:
        return [available_width * 0.28, available_width * 0.72]
    if col_count == 3:
        return [available_width * 0.24, available_width * 0.38, available_width * 0.38]
    if col_count == 4:
        return [available_width * 0.18, available_width * 0.26, available_width * 0.28, available_width * 0.28]
    return [available_width / col_count for _ in range(col_count)]


def make_table(lines: list[str], style_map: dict[str, ParagraphStyle], width: float) -> Table | None:
    rows = [split_table_row(line) for line in lines if not is_table_separator(line)]
    if not rows:
        return None

    col_count = max(len(row) for row in rows)
    normalized = [row + [""] * (col_count - len(row)) for row in rows]
    data = []
    for row_index, row in enumerate(normalized):
        cell_style = style_map["table_header"] if row_index == 0 else style_map["table"]
        data.append([Paragraph(inline_markdown(cell), cell_style) for cell in row])

    table = Table(data, colWidths=column_widths(col_count, width), repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5f0ff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def make_code_block(code: str, style_map: dict[str, ParagraphStyle], width: float) -> Table:
    pre = Preformatted(escape(code.rstrip()), style_map["code"], maxLineLength=96)
    table = Table([[pre]], colWidths=[width], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def parse_markdown(markdown: str, style_map: dict[str, ParagraphStyle], width: float) -> list:
    story = []
    lines = markdown.splitlines()
    i = 0
    first_title = True

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            story.append(Spacer(1, 3))
            i += 1
            continue

        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            story.append(make_code_block("\n".join(code_lines), style_map, width))
            story.append(Spacer(1, 8))
            i += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i])
                i += 1
            table = make_table(table_lines, style_map, width)
            if table is not None:
                story.append(table)
                story.append(Spacer(1, 9))
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            text = inline_markdown(heading.group(2))
            if level == 1 and first_title:
                story.append(Paragraph(text, style_map["title"]))
                story.append(Spacer(1, 4))
                first_title = False
            elif level == 1:
                story.append(PageBreak())
                story.append(Paragraph(text, style_map["title"]))
            elif level == 2:
                story.append(Paragraph(text, style_map["h2"]))
            elif level == 3:
                story.append(Paragraph(text, style_map["h3"]))
            else:
                story.append(Paragraph(text, style_map["h4"]))
            i += 1
            continue

        numbered = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if numbered:
            story.append(
                Paragraph(
                    inline_markdown(numbered.group(2)),
                    style_map["number"],
                    bulletText=f"{numbered.group(1)}.",
                )
            )
            i += 1
            continue

        if stripped.startswith("- "):
            story.append(
                Paragraph(
                    inline_markdown(stripped[2:]),
                    style_map["bullet"],
                    bulletText="-",
                )
            )
            i += 1
            continue

        paragraph_lines = [stripped]
        i += 1
        while i < len(lines):
            next_line = lines[i].strip()
            if (
                not next_line
                or next_line.startswith("#")
                or next_line.startswith("- ")
                or re.match(r"^\d+\.\s+", next_line)
                or next_line.startswith("|")
                or next_line.startswith("```")
            ):
                break
            paragraph_lines.append(next_line)
            i += 1

        paragraph = " ".join(paragraph_lines)
        if "작성일:" in paragraph or "프로젝트명:" in paragraph or "프로젝트 유형:" in paragraph:
            story.append(Paragraph(inline_markdown(paragraph), style_map["subtitle"]))
        else:
            story.append(Paragraph(inline_markdown(paragraph), style_map["body"]))

    return story


def draw_page(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#e5e7eb"))
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, height - 17 * mm, width - doc.rightMargin, height - 17 * mm)
    canvas.setFont(FONT_REGULAR, 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(doc.leftMargin, 10 * mm, "RepoWise AI Project Plan")
    canvas.drawRightString(width - doc.rightMargin, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf() -> Path:
    register_fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title="RepoWise AI 전체 프로젝트 기획서",
        author="RepoWise AI",
    )

    style_map = styles()
    markdown = SOURCE.read_text(encoding="utf-8")
    story = parse_markdown(markdown, style_map, doc.width)
    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return OUTPUT


if __name__ == "__main__":
    try:
        output_path = build_pdf()
    except Exception as exc:
        print(f"Failed to generate PDF: {exc}", file=sys.stderr)
        raise
    print(output_path)
