---
name: delivery-note-json-extractor
description: 从一个或多个发货单、配货单或拣货单 PDF 中提取交付日期、完整订单号、平台 SKC、颜色和数量，输出严格 JSON 或固定默认样式 XLSX。支持 SHEIN 新旧版、TK/POCY、TEMU 及合并单。
---

# Delivery Note JSON Extractor

## Extract and validate

1. Process every page, order, and source document in each PDF. Read the shared rules and applicable layout sections in [extraction-rules.md](references/extraction-rules.md).
2. Prefer model-native PDF/vision reading. Confirm access to first, middle, continuation, and last pages; inspect every page before constructing JSON. If all required fields, table rows, and printed totals are legible and attributable, extract directly without PDF reading or text-extraction tools.
3. Use PDF tools and the bundled parser only when native reading is unavailable, incomplete, or cannot reliably resolve table structure. Render representative pages to confirm layout, then run:

```bash
python3 scripts/extract_delivery_note_pdf.py input.pdf --output extracted.json --pretty --show-format
```

4. On unsupported pages, missing text, or date/total inconsistencies, inspect the rendered source and apply the extraction rules. Use OCR only for absent or unusable text layers. Stop and report unresolved fields, bindings, dates, or totals; never invent values.
5. Before delivery, verify source-document reconciliation, final JSON record count and total quantity, and agreement with any XLSX rows.

Resolve `scripts/` relative to this `SKILL.md`; use task-workspace paths for inputs and outputs. Use the existing Python 3.12 environment and its preinstalled `pdfplumber`; install only if its import fails. Prefer complete `.py` sources; do not execute or decompile uploaded `.pyc` files when source is available.

## Output

Return raw extraction JSON in exactly this shape; apply all field, merge, and zero-row rules from the extraction reference:

```json
{
  "delivery_date": "YYYY-MM-DD",
  "items": [
    {
      "order_number": "",
      "platform_skc": "",
      "attribute_set": "",
      "quantity": 1
    }
  ]
}
```

For spreadsheet-ready JSON, run:

```bash
python3 scripts/format_delivery_records.py extracted.json --pretty
```

For XLSX, read [xlsx-output.md](references/xlsx-output.md) and use its canonical writer to create one workbook per input PDF. The writer accepts raw extraction JSON directly; a separate formatter run is unnecessary.
