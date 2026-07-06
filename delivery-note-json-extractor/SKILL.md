---
name: "Delivery Note JSON Extractor"
description: "从商品发货单（配货单）PDF中提取关键商品信息，并输出严格的JSON格式或写入本地XLSX文件用于电子表格导入。Codex需要解析送货单（配货单）PDF文本、标准化送货日期、去重订单号、提取YY与NQL/L/CSP之间的平台SKC数字、清理颜色属性集、按订单号汇总数量，并将结果转换为表格就绪的JSON或Excel文件时使用。"
---

# Delivery Note JSON Extractor

## Overview

将商品发货单（配货单）PDF提取为严格的JSON格式，然后将其转换为电子表格可用的记录。可按需输出表格就绪的JSON字符串，或直接写入本地`.xlsx`文件。使用LLM提取的参考规则以及捆绑的脚本进行确定性分组和输出格式化。

## Workflow

1. Obtain the raw PDF text from the uploaded PDF. If only a PDF file is available, first extract page text with an available PDF text tool.
2. Read `references/extraction-rules.md`.
3. Extract the delivery date and each item into this exact JSON shape:

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

4. Run `scripts/format_delivery_records.py` on the extracted JSON to output a strict JSON format for spreadsheet import:

```bash
python3 /Users/moorigin/.codex/skills/delivery-note-json-extractor/scripts/format_delivery_records.py extracted.json --pretty
```

The script returns:

```json
{
  "result": "[{\"交付日期\":\"2026-01-01\",\"订单号\":\"...\",\"平台SKC\":\"...\",\"属性集\":\"...\",\"数量\":1}]"
}
```

5. If the user asks for a local Excel file, XLSX file, spreadsheet file, or direct file output, run `scripts/write_delivery_records_xlsx.py` on the same extracted JSON:

```bash
python3 /Users/moorigin/.codex/skills/delivery-note-json-extractor/scripts/write_delivery_records_xlsx.py extracted.json --output delivery_records.xlsx --pretty
```

The script writes a local `.xlsx` workbook with columns:

```text
交付日期, 订单号, 平台SKC, 属性集, 数量
```

It also prints:

```json
{
  "xlsx": "/absolute/path/to/delivery_records.xlsx",
  "rows": 1
}
```

## Extraction Constraints

- Output strict JSON only when the user asks for extraction output. Do not include Markdown fences or explanatory prose.
- Ignore unrelated PDF text such as `商家名称`.
- Normalize delivery dates to `YYYY-MM-DD`.
- Keep one record per unique order number after quantities are summed.
- Extract `platform_skc` only from digits between `YY` and `NQL`, `L`, `CSX`, or `CSP`.
- Clean `attribute_set` down to the color string, removing codes, punctuation, spaces, and size suffixes.
- Use `null` or `""` for missing values.

## Validation

- Check that the JSON parses.
- Check each item has `order_number`, `platform_skc`, `attribute_set`, and numeric `quantity`.
- Run the formatter script before table import.
- When writing XLSX, use `write_delivery_records_xlsx.py` and verify the reported row count matches the expected deduplicated order count.
- If PDF text is image-only or unreadable, state that OCR is required before extraction.
