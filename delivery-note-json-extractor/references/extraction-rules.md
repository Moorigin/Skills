# Delivery Note Extraction Rules

Use this reference for model-native PDF extraction, fallback parser validation, or any page the deterministic parser cannot complete safely.

## Shared contract

Return one JSON object with `delivery_date` and `items`. Each item must contain `order_number`, `platform_skc`, `attribute_set`, and numeric `quantity`.

1. Process every page. Do not stop after the first source document in a merged PDF.
2. Normalize Unicode compatibility glyphs and remove whitespace inside identifiers for matching. Normalize extracted glyph variants such as `⻩` to the source character `黄`; keep table columns and document boundaries intact.
3. Preserve the complete source order number. Rejoin wrapped identifiers, but never drop a numeric suffix such as `-1`: `PB2606300307555-1` must remain unchanged.
4. Extract `platform_skc` as the first consecutive digit run after `YY`, allowing optional ASCII letters between `YY` and that digit run. Preserve leading zeros and stop at the first non-digit after the run. Examples: `YY059NQL` -> `059`, `YYA010L` -> `010`, `ZXYYA010L` -> `010`, `YY12345ABC` -> `12345`, and `YY88008` -> `88008`.
5. Remove only terminal size markers from colors, such as `-XXS`, `-XS`, `-S`, `-M`, `-L`, `-XL`, `-XXL`, `-3XL`, and `-均码`. Remove embedded codes such as `JC076` while preserving meaningful Chinese color words.
6. Merge by `(order_number, platform_skc, attribute_set)`. Preserve conflicting SKCs or colors as separate records.
7. Use printed totals only for reconciliation. Never add both detail rows and totals.
8. Require a single delivery date across one merged input file. Stop and report all conflicting dates instead of selecting the first.

## SHEIN 新版配货单合并文件

Detect from `SHEIN订单号`, `供应商货号`, `颜色/尺码`, and `实发数量`.

- Group consecutive pages by the `FH...` value shown in `配货单 - FH...` or `发货单号`. Treat pages with the same FH as one source document.
- Use one unified parsing route for both table shapes:
  - When a row-level `订单号` column exists, rejoin its wrapped `PB...` cell, including a source suffix such as `-1`, and use the complete identifier.
  - When that column is absent, require exactly one PB order in that page's `SHEIN订单号` header and propagate it to all detail rows.
- Carry the last row order and supplier goods number across continuation pages of the same FH only when a merged cell is blank.
- Validate complete row orders, including numeric suffixes, against the full PB list in that FH header. Do not assign all rows in a multi-order table to the first header order.
- Use `预约取件时间` as `delivery_date`; fall back to `打印时间` only when pickup time is absent.
- Read `platform_skc` from `供应商货号`, not the long `sz...` value in `SKC`.
- Read `attribute_set` from `颜色/尺码`, not the parenthetical supplier color label.
- Sum `实发数量` by business key. Include zero as a valid contribution.
- Reconcile the sum across all pages of the FH against the unique printed grand total. Do not compare a continuation page's partial rows to the repeated grand total in isolation.

## SHEIN 旧版发货单合并文件

Detect from `发货单`, `订单号`, `平台SKC/商家货号`, `平台SKU`, `属性集`, and `数量`.

- Treat each `FH...` as one source document; process every FH/page in the merged PDF.
- Use `送货时间` as `delivery_date`; fall back to `确认提交时间` only when needed.
- Use the complete PB value in the row-level `订单号` column and preserve a numeric suffix such as `-1`.
- In `平台SKC/商家货号`, ignore the long `sz...` platform identifier and extract the YY code from the same cell or its immediately following continuation row.
- Use `属性集` for color and remove the size suffix.
- Use the row-level `数量`; reconcile all detail rows in the FH against its printed `合计`.

## TK/POCY 拣货单合并文件

Detect from `订单号: POCY...`, `下单时间`, `要求发货时间`, `SKU货号`, and `下单数量`.

- Process every POCY block on every page.
- Use `要求发货时间`, not `下单时间`.
- Use the block's POCY order number.
- Read platform SKC from `SKU货号`/`货号`; repair a split `N` + `QL`.
- Use `产品信息` -> `颜色:` for color.
- Sum `下单数量` size rows or use its `合计`; ignore `未发货`, `待揽收`, and empty `拣货数`.

## TEMU 备货拣货单合并文件

Detect from `SKC货号`, `备货母单号`, `备货单号`, `属性集`, and `数量`.

- Process every numbered product group on every page.
- Use `要求发货时间`, not `打印时间` or `创建时间`.
- Use `备货单号` (`WB...`); fall back to `备货母单号` (`WP...`) only when WB is absent.
- Read platform SKC from `SKC货号`/`SKU货号`, not numeric `SKC` or `SKU ID`.
- Read color from `属性集` and quantity from `数量`, not `拣货数`.
- Sum size rows and reconcile each group's `合计`.

## Ambiguity handling

- Stop when a page's table signature matches no supported layout.
- Stop when a SHEIN page lacks an FH and cannot safely inherit the immediately preceding FH.
- Stop when a required order, YY code, color, or quantity cannot be bound to a detail row.
- Use OCR only for image-only or unusable text layers; do not use nearby unrelated numbers as substitutes.
