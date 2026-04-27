---
name: "Delivery Note JSON Extractor"
description: "从商品发货单PDF中提取关键商品信息，并输出严格的JSON格式用于电子表格导入。当Codex需要解析送货单PDF文本、标准化送货日期、去重订单号、提取YY与NQL/L/CSP之间的平台SKC数字、清理颜色属性集、按订单号汇总数量，并将结果转换为表格就绪的JSON时使用。"
---

# Delivery Note JSON Extractor

## Overview

将商品发货单PDF提取为严格的JSON格式，然后将其转换为电子表格可用的记录。使用LLM提取的参考规则以及捆绑的脚本进行确定性分组和输出格式化。

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
python3 /Users/moorigin/.codex/skills/Delivery-Note-JSON-Extractor/scripts/format_delivery_records.py extracted.json --pretty
```

The script returns:

```json
{
  "result": "[{\"交付日期\":\"2026-01-01\",\"订单号\":\"...\",\"平台SKC\":\"...\",\"属性集\":\"...\",\"数量\":1}]"
}
```

## Extraction Constraints

- Output strict JSON only when the user asks for extraction output. Do not include Markdown fences or explanatory prose.
- Ignore unrelated PDF text such as `商家名称`.
- Normalize delivery dates to `YYYY-MM-DD`.
- Keep one record per unique order number after quantities are summed.
- Extract `platform_skc` only from digits between `YY` and `NQL`, `L`, or `CSP`.
- Clean `attribute_set` down to the color string, removing codes, punctuation, spaces, and size suffixes.
- Use `null` or `""` for missing values.

## Validation

- Check that the JSON parses.
- Check each item has `order_number`, `platform_skc`, `attribute_set`, and numeric `quantity`.
- Run the formatter script before table import.
- If PDF text is image-only or unreadable, state that OCR is required before extraction.
