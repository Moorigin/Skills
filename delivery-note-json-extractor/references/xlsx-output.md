# Fixed XLSX Output

Use `scripts/write_delivery_records_xlsx.py` as the canonical writer, with raw extraction JSON as input:

```bash
python3 scripts/write_delivery_records_xlsx.py extracted.json \
  --output delivery_records.xlsx --sheet-name 发货单 --pretty
```

## Style contract

- Default to one worksheet `发货单`, one header row, and no title or summary rows.
- Columns A:E, in order: `交付日期, 订单号, 平台SKC, 属性集, 数量`; fixed widths: `13, 24, 14, 24, 10`.
- Header A1:E1: workbook default font and size, bold only. Add no fills, borders, alignment, wrapping, or merged cells.
- Every populated body cell in A2:E末行 must use the same Normal/General style (`style 0`), regardless of column or value. Store `数量` as numeric integers and A:D as text, preserving dates, leading zeros, and exact identifiers.
- Add no tables, themes, filters, frozen panes, conditional formatting, hidden rows/columns, extra worksheets, or print styling unless explicitly requested.
- For user-requested appearance changes, alter only the requested elements; keep remaining body cells on the default style.

Use spreadsheet tools only to inspect/render the workbook; do not recreate, resave, or restyle it through a generic spreadsheet workflow unless the user requests a different style. Render every generated worksheet, confirm the five headers are visible and values are not clipped, and verify the style contract without saving from the inspecting application.
