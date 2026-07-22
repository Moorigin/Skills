---
name: delivery-note-json-extractor
description: 从一个或多个商品发货单、配货单或拣货单 PDF 中提取交付日期、完整订单号、平台 SKC、颜色属性和数量，并输出严格 JSON 或固定默认样式的 XLSX；优先使用模型原生 PDF 读取能力，仅在无法完整读取时使用 PDF 工具。用于处理 SHEIN 新旧版、TK/POCY 和 TEMU 合并单；支持按 FH 跨页衔接与订单号残段拼接、保留 PB 的 `-1` 等数字后缀、提取 YY 后可选字母后的首段数字、TK 使用下单时间、TEMU 使用 WB 单号与打印时间、丢弃零数量行及尺码行汇总；XLSX 数据区统一使用 Normal/General 格式。
---

# Delivery Note JSON Extractor

## Workflow

1. Treat each input PDF as a container that may hold many orders and many source documents. Process every page and preserve source-document boundaries.
2. Attempt model-native PDF reading first. Read the attached PDF directly with the model's PDF/vision capability, read `references/extraction-rules.md`, and inspect every page before constructing the Raw JSON Contract. Confirm access to the complete document by checking representative first, middle, continuation, and last pages. When every required field, table row, and printed total is legible and bindable, complete the extraction without invoking a PDF reading or text-extraction tool merely for convenience.
3. Only when model-native reading is unavailable, cannot traverse every page, or cannot reliably read the table structure, use PDF tools and the bundled deterministic parser. Render representative pages for layout confirmation, then resolve `scripts/` relative to this `SKILL.md` and run:

```bash
python3 scripts/extract_delivery_note_pdf.py input.pdf --output extracted.json --pretty --show-format
```

The parser recognizes these merged-file layouts:

- SHEIN 新版配货单: accept pages with or without a row-level `订单号` column through one unified route; join pages by `FH...`.
- SHEIN 旧版发货单: read `平台SKC/商家货号` continuation rows and all orders from each merged page.
- TK/POCY 拣货单: read every POCY order block across all pages and use `下单时间`.
- TEMU 备货拣货单: read every WB product group across all pages and use `打印时间`.

4. If the fallback parser reports an unsupported page, missing text layer, inconsistent date, or inconsistent total, inspect the rendered source and apply `references/extraction-rules.md`. Apply OCR only when the text layer is absent or unusable.
5. Run the formatter when spreadsheet-ready JSON is needed:

```bash
python3 scripts/format_delivery_records.py extracted.json --pretty
```

6. When the user requests XLSX, use the bundled deterministic writer to create one workbook per input PDF:

```bash
python3 scripts/write_delivery_records_xlsx.py extracted.json \
  --output delivery_records.xlsx \
  --sheet-name 发货单 \
  --pretty
```

Keep these columns in this exact order:

```text
交付日期, 订单号, 平台SKC, 属性集, 数量
```

Use spreadsheet tooling only to inspect and render the generated workbook. Do not recreate, resave, or restyle it with a generic spreadsheet workflow unless the user explicitly requests a different style.

## Environment Notes

- Use the preinstalled `pdfplumber` in the Python 3.12 environment. Do not install another copy unless the import actually fails.
- Prefer the complete `.py` source files in `scripts/`. Ignore uploaded `.pyc` files when the corresponding source is available; do not decompile or execute them.

## Fixed XLSX Style Contract

Treat `scripts/write_delivery_records_xlsx.py` as the canonical XLSX writer. Its default output must remain minimal and reproducible:

- Use one worksheet named `发货单` by default, one header row, and no title or summary rows.
- Use fixed column widths `13, 24, 14, 24, 10` for columns A:E.
- Format A1:E1 with the workbook's default font and size plus bold only. Do not add fills, borders, alignment, wrapping, or merged cells.
- Assign every populated body cell in A2:E末行 to the same workbook Normal/General style (`style 0`). Do not vary styles by column or value.
- Store `数量` as a numeric integer. Store delivery dates and identifiers as text so leading zeros and exact source strings are preserved while all body cells retain the same default style.
- Do not add tables, themes, filters, frozen panes, conditional formatting, hidden rows or columns, extra worksheets, or print styling unless the user explicitly requests them.
- If the user requests a different appearance, change only the specifically requested elements and keep the remaining body cells on the default style.

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
      "quantity": 1
    }
  ]
}
```

- Keep `quantity` numeric.
- Discard every item whose quantity is zero before returning JSON and before creating XLSX. Keep zero rows only long enough to reconcile the source's printed totals; never emit rows such as `橙色-L 0`, `白色-L 0`, or `花茶-L 0`.
- Preserve the complete source `order_number`, including numeric suffixes such as `-1`; remove wrapping whitespace but never drop the suffix.
- Extract `platform_skc` as the first consecutive digit run after `YY`, allowing optional ASCII letters between `YY` and the digits. Preserve leading zeros: `YY059NQL` -> `059` and `ZXYYA010L` -> `010`.
- Keep `attribute_set` faithful to the source color after removing only size suffixes and embedded non-color codes; normalize compatibility glyphs such as `⻩` to `黄`.
- Merge size rows only when `order_number`, `platform_skc`, and cleaned `attribute_set` agree.
- Preserve separate records when one order contains different platform SKCs or colors.
- Exclude shipment numbers, logistics numbers, merchant names, images, SKU IDs, SPU IDs, headers, and totals as item records.
- Fail rather than invent a required value when neither model-native reading nor the fallback parser can bind it to the correct document, row, or column.

## Validation

- Require one common semantic delivery date across the merged input. Stop when source documents contain conflicting dates.
- Reconcile detail sums against totals at the source-document level, not page by page. A multi-page SHEIN `FH...` document may repeat the same grand total on every page.
- Validate every complete row-level SHEIN PB order, including a suffix such as `-1`, against that document's page-header order list when the list exists.
- When a continuation page begins with a row containing only an order-number fragment and a blank quantity, join it to the preceding page's trailing PB fragment. If direct concatenation is insufficient, resolve it only when the FH header order list yields one unique prefix/suffix match; then validate the completed order.
- Confirm wrapped `PB...` and `YY...` codes plus old-SHEIN merchant-goods continuation rows are reconstructed. Preserve PB numeric suffixes; for SKC, keep the first consecutive digit run after `YY` and any optional intervening letters, then stop at the following non-digit.
- Confirm `order_number`, `platform_skc`, and cleaned `attribute_set` remain faithful to the source row before merging.
- Confirm zero-quantity source rows contribute zero to reconciliation and are absent from final JSON and XLSX rows.
- Verify the JSON record count, total quantity, and final XLSX rows before delivery.
- Render every generated worksheet for a visual check, but do not save from the inspecting application. Confirm the five headers are visible, values are not clipped, and the workbook still follows the Fixed XLSX Style Contract.
