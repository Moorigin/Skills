#!/usr/bin/env python3
"""Validate packing-list rows and build an aggregated A4 PDF report."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


class InputError(ValueError):
    """Raised when the staging JSON cannot produce a reliable report."""


def clean_text(value: Any, field: str, row_number: int) -> str:
    if value is None:
        raise InputError(f"第 {row_number} 行缺少 {field}")
    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise InputError(f"第 {row_number} 行的 {field} 为空")
    return text


def normalize_style_no(value: Any, row_number: int) -> str:
    """Remove parenthesized annotations before grouping styles."""
    text = clean_text(value, "style_no", row_number)
    kept: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                raise InputError(f"第 {row_number} 行的 style_no 括号不成对，请核对原单")
            depth -= 1
        elif depth == 0:
            kept.append(char)
    if depth:
        raise InputError(f"第 {row_number} 行的 style_no 括号不成对，请核对原单")
    return clean_text("".join(kept), "style_no", row_number)


def parse_quantity(value: Any, row_number: int) -> int:
    if isinstance(value, bool) or value is None:
        raise InputError(f"第 {row_number} 行的 quantity 不是整数")
    raw = str(value).replace(",", "").strip()
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise InputError(f"第 {row_number} 行的 quantity 不是数字: {value!r}") from exc
    if number != number.to_integral_value():
        raise InputError(f"第 {row_number} 行的 quantity 必须为整数: {value!r}")
    integer = int(number)
    if integer < 0:
        raise InputError(f"第 {row_number} 行的 quantity 不能为负数: {integer}")
    return integer


def load_payload(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            data = json.load(stream)
    except FileNotFoundError as exc:
        raise InputError(f"找不到输入文件: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"JSON 格式错误（第 {exc.lineno} 行第 {exc.colno} 列）") from exc

    if isinstance(data, list):
        metadata: dict[str, Any] = {}
        rows = data
    elif isinstance(data, dict):
        metadata = data
        rows = data.get("rows")
    else:
        raise InputError("输入必须是明细数组，或包含 rows 数组的对象")

    if not isinstance(rows, list) or not rows:
        raise InputError("rows 必须是非空数组")
    if not all(isinstance(row, dict) for row in rows):
        raise InputError("rows 中的每一项都必须是对象")
    return metadata, rows


def normalize_and_aggregate(rows: list[dict[str, Any]]) -> tuple[list[tuple[str, str, str, str, int]], int]:
    totals: defaultdict[tuple[str, str, str, str], int] = defaultdict(int)
    skipped_zero = 0
    for index, row in enumerate(rows, 1):
        customer_name = clean_text(row.get("customer_name"), "customer_name（客户名称）", index)
        style_no = normalize_style_no(row.get("style_no"), index)
        color = clean_text(row.get("color"), "color", index)
        size = clean_text(row.get("size"), "size", index)
        quantity = parse_quantity(row.get("quantity"), index)
        if quantity == 0:
            skipped_zero += 1
            continue
        totals[(customer_name, style_no, color, size)] += quantity

    if not totals:
        raise InputError("没有可汇总的正数量明细")

    aggregated = [(*key, quantity) for key, quantity in totals.items()]
    aggregated.sort(key=lambda row: (natural_key(row[0]), row[0], natural_key(row[1]), row[1], natural_key(row[2]), row[2], size_key(row[3]), row[3]))
    return aggregated, skipped_zero


def natural_key(value: str) -> tuple[tuple[int, Any], ...]:
    parts = re.split(r"(\d+(?:\.\d+)?)", value.casefold())
    key: list[tuple[int, Any]] = []
    for part in parts:
        if not part:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", part):
            key.append((0, Decimal(part)))
        else:
            key.append((1, part))
    return tuple(key)


def size_key(value: str) -> tuple[int, Any, tuple[tuple[int, Any], ...]]:
    compact = re.sub(r"[\s_-]+", "", unicodedata.normalize("NFKC", value)).upper()
    named_order = {
        "XXXS": 0,
        "XXS": 1,
        "XS": 2,
        "S": 3,
        "M": 4,
        "L": 5,
        "XL": 6,
        "0XL": 6,
        "1XL": 7,
        "XXL": 8,
        "2XL": 8,
        "XXXL": 9,
        "3XL": 9,
        "4XL": 10,
        "5XL": 11,
        "6XL": 12,
        "ONESIZE": 90,
        "OS": 90,
        "FREE": 90,
        "均码": 90,
    }
    if compact in named_order:
        return (0, named_order[compact], natural_key(value))
    if re.fullmatch(r"\d+(?:\.\d+)?", compact):
        return (1, Decimal(compact), natural_key(value))
    return (2, compact, natural_key(value))


def register_cjk_font() -> str:
    candidates = [
        ("SummaryCJK", "/System/Library/Fonts/PingFang.ttc", 0),
        ("SummaryCJK", "/System/Library/Fonts/STHeiti Medium.ttc", 0),
        ("SummaryCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
        ("SummaryCJK", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
        ("SummaryCJK", "/Library/Fonts/Arial Unicode.ttf", 0),
    ]
    for name, filename, subfont_index in candidates:
        if not Path(filename).exists():
            continue
        try:
            pdfmetrics.registerFont(
                TTFont(name, filename, validate=0, subfontIndex=subfont_index)
            )
            pdfmetrics.registerFontFamily(
                name, normal=name, bold=name, italic=name, boldItalic=name
            )
            return name
        except Exception:
            continue

    fallback = "STSong-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(fallback))
    pdfmetrics.registerFontFamily(
        fallback, normal=fallback, bold=fallback, italic=fallback, boldItalic=fallback
    )
    return fallback


def safe_paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(value)), style)


def unique_source_count(metadata: dict[str, Any]) -> int | None:
    sources = metadata.get("source_files")
    if not isinstance(sources, list):
        return None
    normalized = {
        unicodedata.normalize("NFKC", str(source)).strip()
        for source in sources
        if str(source).strip()
    }
    return len(normalized) or None


def grouped_cell_commands(
    rows: list[tuple[str, str, str, str, int]],
    max_merged_rows: int = 20,
) -> list[tuple[Any, ...]]:
    """Build page-safe row spans for style, style-total, and color cells."""
    commands: list[tuple[Any, ...]] = []
    style_start = 0
    style_group_index = 0

    while style_start < len(rows):
        style_key = rows[style_start][:2]
        style_end = style_start
        while style_end + 1 < len(rows) and rows[style_end + 1][:2] == style_key:
            style_end += 1

        background = (
            colors.white
            if style_group_index % 2 == 0
            else colors.HexColor("#F5F8FB")
        )
        commands.append(
            ("BACKGROUND", (0, style_start + 1), (-1, style_end + 1), background)
        )
        commands.append(
            (
                "LINEABOVE",
                (0, style_start + 1),
                (-1, style_start + 1),
                0.8,
                colors.HexColor("#7E96AA"),
            )
        )

        color_ranges: list[tuple[int, int]] = []
        color_start = style_start
        while color_start <= style_end:
            color = rows[color_start][2]
            color_end = color_start
            while color_end + 1 <= style_end and rows[color_end + 1][2] == color:
                color_end += 1
            color_ranges.append((color_start, color_end))
            color_start = color_end + 1

        style_chunks: list[tuple[int, int]] = []
        color_chunks: list[tuple[int, int]] = []
        pending_start: int | None = None
        pending_end: int | None = None
        pending_length = 0

        for color_start, color_end in color_ranges:
            color_length = color_end - color_start + 1
            if color_length > max_merged_rows:
                if pending_start is not None and pending_end is not None:
                    style_chunks.append((pending_start, pending_end))
                    pending_start = None
                    pending_end = None
                    pending_length = 0
                segment_start = color_start
                while segment_start <= color_end:
                    segment_end = min(segment_start + max_merged_rows - 1, color_end)
                    style_chunks.append((segment_start, segment_end))
                    color_chunks.append((segment_start, segment_end))
                    segment_start = segment_end + 1
                continue

            if pending_start is not None and pending_length + color_length > max_merged_rows:
                if pending_end is None:
                    raise AssertionError("pending merged range is incomplete")
                style_chunks.append((pending_start, pending_end))
                pending_start = None
                pending_end = None
                pending_length = 0

            if pending_start is None:
                pending_start = color_start
            pending_end = color_end
            pending_length += color_length
            color_chunks.append((color_start, color_end))

        if pending_start is not None and pending_end is not None:
            style_chunks.append((pending_start, pending_end))

        for chunk_start, chunk_end in style_chunks:
            if chunk_end > chunk_start:
                commands.append(
                    ("SPAN", (1, chunk_start + 1), (1, chunk_end + 1))
                )
                commands.append(
                    ("SPAN", (5, chunk_start + 1), (5, chunk_end + 1))
                )
        for chunk_start, chunk_end in color_chunks:
            if chunk_end > chunk_start:
                commands.append(
                    ("SPAN", (2, chunk_start + 1), (2, chunk_end + 1))
                )

        style_group_index += 1
        style_start = style_end + 1

    return commands


def build_pdf(
    output_path: Path,
    metadata: dict[str, Any],
    input_row_count: int,
    rows: list[tuple[str, str, str, str, int]],
    skipped_zero: int,
    title_override: str | None,
) -> dict[str, Any]:
    font_name = register_cjk_font()
    title = clean_text(
        title_override or metadata.get("title") or "配货单款色码汇总",
        "title",
        0,
    )
    generated_at = metadata.get("generated_at")
    if generated_at is None:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    else:
        generated_at = clean_text(generated_at, "generated_at", 0)

    total_quantity = sum(row[4] for row in rows)
    style_count = len({row[1] for row in rows})
    style_totals: defaultdict[tuple[str, str], int] = defaultdict(int)
    customer_totals: defaultdict[str, int] = defaultdict(int)
    for customer_name, style_no, _color, _size, quantity in rows:
        style_totals[(customer_name, style_no)] += quantity
        customer_totals[customer_name] += quantity
    source_count = unique_source_count(metadata)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=15 * mm,
        bottomMargin=17 * mm,
        title=title,
        author="Codex",
        subject="配货单款号、颜色、尺码和数量汇总",
    )

    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCJK",
        parent=base_styles["Title"],
        fontName=font_name,
        fontSize=20,
        leading=26,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#17324D"),
        spaceAfter=4 * mm,
    )
    meta_style = ParagraphStyle(
        "MetaCJK",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=8,
        leading=10,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#667085"),
    )
    label_style = ParagraphStyle(
        "LabelCJK",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#52606D"),
    )
    value_style = ParagraphStyle(
        "ValueCJK",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=12,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#17324D"),
    )
    cell_style = ParagraphStyle(
        "CellCJK",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=8.5,
        leading=11,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#1F2937"),
        splitLongWords=True,
    )
    centered_cell_style = ParagraphStyle(
        "CenteredCellCJK",
        parent=cell_style,
        alignment=TA_CENTER,
    )
    story: list[Any] = [safe_paragraph(title, title_style)]
    story.append(safe_paragraph(f"生成时间：{generated_at}", meta_style))
    story.append(Spacer(1, 3 * mm))

    labels = ["来源文件", "店铺数", "原始明细", "汇总组合", "款号数", "总数量"]
    values = [
        str(source_count) if source_count is not None else "-",
        str(len(customer_totals)),
        str(input_row_count - skipped_zero),
        str(len(rows)),
        str(style_count),
        str(total_quantity),
    ]
    stats = Table(
        [
            [safe_paragraph(label, label_style) for label in labels],
            [safe_paragraph(value, value_style) for value in values],
        ],
        colWidths=[(document.width - 12) / 6] * 6,
        hAlign="LEFT",
        rowHeights=[7 * mm, 10 * mm],
    )
    stats.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F6F9")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7E0E8")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
            ]
        )
    )
    story.extend([stats, Spacer(1, 5 * mm)])

    shop_heading_style = ParagraphStyle(
        "ShopHeadingCJK", parent=cell_style, fontSize=11, leading=15,
        alignment=TA_LEFT, textColor=colors.HexColor("#17324D"),
    )
    # Repeat the borderless shop label above the column headings on continuation pages.
    table_width = document.width - 12  # SimpleDocTemplate frame has 6 pt padding per side.
    widths = [table_width * weight / 182 for weight in (12, 47, 39, 27, 25, 32)]
    for customer_name, customer_total in customer_totals.items():
        shop_rows = [row for row in rows if row[0] == customer_name]
        table_rows: list[list[Any]] = [
            [safe_paragraph(f"店铺：{customer_name}", shop_heading_style), "", "", "", "", ""],
            ["序号", "款号", "颜色", "尺码", "数量", "店内款号总数"],
        ]
        for index, (_customer, style_no, color, size, quantity) in enumerate(shop_rows, 1):
            table_rows.append([
                safe_paragraph(value, centered_cell_style)
                for value in (index, style_no, color, size, quantity,
                              style_totals[(customer_name, style_no)])
            ])
        table_rows.append(["店铺发货总数", "", "", "", "", str(customer_total)])
        detail_table = LongTable(table_rows, colWidths=widths, repeatRows=2, hAlign="LEFT")
        # The grouping helper counts one header; shift its row coordinates for the label.
        group_commands = [
            (cmd[0], (cmd[1][0], cmd[1][1] + 1),
             (cmd[2][0], cmd[2][1] + 1), *cmd[3:])
            for cmd in grouped_cell_commands(shop_rows)
        ]
        detail_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 1), (-1, 1), colors.white),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#244A6A")),
            ("ALIGN", (0, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 1), (-1, -1), .4, colors.HexColor("#B8C6D1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ("SPAN", (0, 0), (-1, 0)),
            ("LEFTPADDING", (0, 0), (-1, 0), 0),
            ("ALIGN", (0, 0), (-1, 0), "LEFT"),
            ("SPAN", (0, -1), (4, -1)),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E7EEF5")),
            ("LINEABOVE", (0, -1), (-1, -1), .8, colors.HexColor("#244A6A")),
        ] + group_commands))
        story.extend([detail_table, Spacer(1, 5 * mm)])

    def decorate_page(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D0D7DE"))
        canvas.setLineWidth(0.4)
        canvas.line(14 * mm, 12 * mm, A4[0] - 14 * mm, 12 * mm)
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(14 * mm, 7.5 * mm, title)
        canvas.drawRightString(A4[0] - 14 * mm, 7.5 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    document.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return {
        "output_pdf": str(output_path.resolve()),
        "input_rows": input_row_count,
        "skipped_zero_rows": skipped_zero,
        "aggregated_rows": len(rows),
        "style_count": style_count,
        "customer_count": len(customer_totals),
        "customer_totals": dict(customer_totals),
        "total_quantity": total_quantity,
        "page_size": "A4 portrait",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将已核对的配货单款色码 JSON 汇总为 A4 PDF。"
    )
    parser.add_argument("--input-json", required=True, type=Path, help="UTF-8 JSON 输入")
    parser.add_argument("--output-pdf", required=True, type=Path, help="输出 PDF 路径")
    parser.add_argument("--title", help="覆盖报告标题")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        metadata, input_rows = load_payload(args.input_json)
        rows, skipped_zero = normalize_and_aggregate(input_rows)
        result = build_pdf(
            args.output_pdf,
            metadata,
            len(input_rows),
            rows,
            skipped_zero,
            args.title,
        )
    except (InputError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
