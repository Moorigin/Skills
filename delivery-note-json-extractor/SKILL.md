---
name: delivery-note-json-extractor
description: 从一个或多个商品发货单、配货单或拣货单 PDF 中提取交付日期、订单号、平台 SKC、颜色属性和数量，并输出严格 JSON 或 XLSX。用于处理合并了多个订单或多个发货单的 SHEIN 新版配货单、SHEIN 旧版发货单、TK/POCY 拣货单和 TEMU 备货拣货单；支持按 FH 发货单号跨页衔接、同一 SHEIN 文件内页眉单订单与表格多订单的自动取号、商家货号续行、PB/YY 编码换行修复、提取 YY 后连续数字及尺码行汇总。
---

# Delivery Note JSON Extractor

## Workflow

1. Treat each input PDF as a container that may hold many orders and many source documents. Render representative first, middle, continuation, and last pages before trusting flattened text.
2. Run the deterministic parser. Resolve `scripts/` relative to this `SKILL.md`:

```bash
python3 scripts/extract_delivery_note_pdf.py input.pdf --output extracted.json --pretty --show-format
```

The parser recognizes these merged-file layouts:

- SHEIN 新版配货单: accept pages with or without a row-level `订单号` column through one unified route; join pages by `FH...`.
- SHEIN 旧版发货单: read `平台SKC/商家货号` continuation rows and all orders from each merged page.
- TK/POCY 拣货单: read every POCY order block across all pages.
- TEMU 备货拣货单: read every WB/WP product group across all pages.

3. If the parser reports an unsupported page, missing text layer, inconsistent date, or inconsistent total, inspect the rendered source and read `references/extraction-rules.md`. Apply OCR only when the text layer is absent or unusable.
4. Run the formatter when spreadsheet-ready JSON is needed:

```bash
python3 scripts/format_delivery_records.py extracted.json --pretty
```

5. When the user requests XLSX, use the Spreadsheets workflow to create and visually verify one workbook per input PDF with these columns:

```text
交付日期, 订单号, 平台SKC, 属性集, 数量
```

## Raw JSON Contract

Return exactly this shape for extraction output:

```json
{
  "delivery_date": "YYYY-MM-DD",
  "items": [
    {
      "order_number": "",
      "platform_skc": "",
      "attribute_set": "",
      "quantity": 0
    }
  ]
}
```

- Keep `quantity` numeric.
- Merge size rows only when `order_number`, `platform_skc`, and cleaned `attribute_set` agree.
- Preserve separate records when one order contains different platform SKCs or colors.
- Exclude shipment numbers, logistics numbers, merchant names, images, SKU IDs, SPU IDs, headers, and totals as item records.
- Fail rather than invent a required value when the deterministic parser cannot bind it to the correct document, row, or column.

## Validation

- Require one common semantic delivery date across the merged input. Stop when source documents contain conflicting dates.
- Reconcile detail sums against totals at the source-document level, not page by page. A multi-page SHEIN `FH...` document may repeat the same grand total on every page.
- Validate every row-level SHEIN PB order against that document's page-header order list when the list exists.
- Confirm wrapped `PB...` and `YY...` codes plus old-SHEIN merchant-goods continuation rows are reconstructed; keep only the consecutive digits immediately after `YY` regardless of the following suffix.
- Confirm zero-quantity rows contribute zero without being mistaken for missing quantities.
- Verify the JSON record count, total quantity, and final XLSX rows before delivery.
