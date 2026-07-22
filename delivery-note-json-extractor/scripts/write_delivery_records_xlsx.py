#!/usr/bin/env python3
"""Write extracted delivery-note JSON to a fixed, default-style XLSX workbook."""

from __future__ import annotations

import argparse
import json
import posixpath
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from format_delivery_records import main as format_delivery_records


HEADERS = ["交付日期", "订单号", "平台SKC", "属性集", "数量"]
DEFAULT_CELL_STYLE = 0
HEADER_CELL_STYLE = 1
COLUMN_WIDTHS = (13, 24, 14, 24, 10)


def _clean_sheet_name(value: str) -> str:
    invalid_chars = set('[]:*?/\\')
    sheet_name = "".join("_" if char in invalid_chars else char for char in value.strip())
    return (sheet_name or "发货单")[:31]


def _cell_ref(column_index: int, row_index: int) -> str:
    column = ""
    number = column_index
    while number:
        number, remainder = divmod(number - 1, 26)
        column = chr(65 + remainder) + column
    return f"{column}{row_index}"


def _string_cell(column_index: int, row_index: int, value: Any, style: int | None = None) -> str:
    cell_ref = _cell_ref(column_index, row_index)
    style_attr = f' s="{style}"' if style is not None else ""
    text = escape("" if value is None else str(value))
    return f'<c r="{cell_ref}" t="inlineStr"{style_attr}><is><t>{text}</t></is></c>'


def _number_cell(
    column_index: int,
    row_index: int,
    value: Any,
    style: int | None = None,
) -> str:
    cell_ref = _cell_ref(column_index, row_index)
    style_attr = f' s="{style}"' if style is not None else ""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return f'<c r="{cell_ref}"{style_attr}><v>{number}</v></c>'


def _worksheet_xml(records: list[dict[str, Any]]) -> str:
    rows = []
    header_cells = [
        _string_cell(index, 1, header, style=HEADER_CELL_STYLE)
        for index, header in enumerate(HEADERS, start=1)
    ]
    rows.append(f'<row r="1">{"".join(header_cells)}</row>')

    for row_index, record in enumerate(records, start=2):
        cells = []
        for column_index, header in enumerate(HEADERS, start=1):
            value = record.get(header)
            if header == "数量":
                cells.append(
                    _number_cell(
                        column_index,
                        row_index,
                        value,
                        style=DEFAULT_CELL_STYLE,
                    )
                )
            else:
                cells.append(
                    _string_cell(
                        column_index,
                        row_index,
                        value,
                        style=DEFAULT_CELL_STYLE,
                    )
                )
        rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    dimension = f"A1:E{max(len(records) + 1, 1)}"
    columns = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(COLUMN_WIDTHS, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="{dimension}"/>'
        f'<cols>{columns}</cols>'
        f'<sheetData>{"".join(rows)}</sheetData>'
        '</worksheet>'
    )


def _workbook_xml(sheet_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>'
        f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
        '</sheets>'
        '</workbook>'
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def _workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )


def _doc_props_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Codex</Application>'
        '</Properties>'
    )


def write_xlsx(records: list[dict[str, Any]], output_path: Path, sheet_name: str = "发货单") -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_sheet_name = _clean_sheet_name(sheet_name)
    parts = {
        "[Content_Types].xml": _content_types_xml(),
        "_rels/.rels": _root_rels_xml(),
        "docProps/app.xml": _doc_props_xml(),
        "xl/workbook.xml": _workbook_xml(safe_sheet_name),
        "xl/_rels/workbook.xml.rels": _workbook_rels_xml(),
        "xl/styles.xml": _styles_xml(),
        "xl/worksheets/sheet1.xml": _worksheet_xml(records),
    }

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        for name, content in parts.items():
            workbook.writestr(posixpath.normpath(name), content)
    return output_path


def records_from_text(raw: str) -> list[dict[str, Any]]:
    formatted = format_delivery_records(raw)
    try:
        records = json.loads(formatted.get("result", "[]"))
    except json.JSONDecodeError:
        return []
    return records if isinstance(records, list) else []


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="Path to extracted JSON. Reads stdin if omitted.")
    parser.add_argument("--output", "-o", default="delivery_records.xlsx", help="XLSX output path.")
    parser.add_argument("--sheet-name", default="发货单", help="Worksheet name, max 31 characters.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON status output.")
    args = parser.parse_args()

    if args.input:
        raw = Path(args.input).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    records = records_from_text(raw)
    output_path = write_xlsx(records, Path(args.output).expanduser().resolve(), args.sheet_name)
    status = {"xlsx": str(output_path), "rows": len(records), "style": "fixed-default"}
    print(json.dumps(status, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
