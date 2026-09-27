# Delivery Note Extraction Rules

Apply the shared rules and each layout present in the PDF, for both native extraction and parser fallback. For SHEIN, also read its shared document rules.

## Shared rules

- Preserve table columns and source-document boundaries. Normalize Unicode compatibility glyphs (e.g. `⻩` → `黄`, `⻘` → `青`) and remove identifier wrapping whitespace.
- Skip verified blank pages containing only print headers/footers. A missing table or text layer alone does not prove a page is blank; inspect its rendering and use OCR for unreadable image content.
- Rejoin wrapped `PB...` and `YY...` identifiers. Preserve the complete order number, including numeric suffixes: `PB2606300307555-1` stays unchanged.
- For `platform_skc`, take the first consecutive digit run after `YY`, allowing optional intervening ASCII letters. Preserve leading zeros. Include the complete literal `DML` only if it immediately follows the digits, then stop; otherwise stop at the first non-digit. Examples: `YY059NQL` → `059`, `ZXYYA010L` → `010`, `2506YY25103DML` → `25103DML`.
- For `attribute_set`, retain the source color; remove only terminal size markers (e.g. `-XXS`, `-XS`, `-S`, `-M`, `-L`, `-XL`, `-XXL`, `-3XL`, `-均码`) and embedded non-color codes such as `JC076`. Preserve meaningful Chinese color words.
- Keep quantities numeric. Count zero rows during reconciliation, then discard them from all JSON/XLSX outputs. Merge positive size rows only by identical `(order_number, platform_skc, cleaned attribute_set)` after verifying source bindings; different SKCs or colors remain separate.
- Totals are checks, never additional items. Exclude shipment/logistics numbers, merchant names, images, SKU/SPU IDs, headers, and totals as item records.
- Require one semantic delivery date (`YYYY-MM-DD`) per merged input PDF, using the layout-specific fields below. Report all conflicting dates and stop.
- Stop for unsupported table signatures, conflicting printed totals, detail/total mismatches, or required orders, YY codes, colors, or quantities that cannot be bound to the correct document and row. Never substitute nearby unrelated values.

## SHEIN — shared document rules

- Group consecutive pages by `FH...` in `配货单 - FH...` or `发货单号`. A missing FH may inherit only the immediately preceding FH when the continuation is unambiguous; otherwise stop.
- Reconcile all detail rows in each FH against its unique printed grand total/`合计`. A grand total repeated on several pages counts once; never compare a partial page to the whole-document total.
- Validate complete row-level PB orders, including suffixes, against that FH's full header order list whenever present.

## SHEIN 新版配货单

Signature: `SHEIN订单号`, `供应商货号`, `颜色/尺码`, `实发数量`.

- Date: `预约取件时间`; use `打印时间` only when pickup time is absent.
- Use one route for both table shapes: use the complete row-level `订单号` when the column exists; otherwise require exactly one PB in that page's `SHEIN订单号` header and assign it to its detail rows. Never assign a multi-order table to the first header order.
- Carry the last row order and supplier goods number across continuation pages of the same FH only for blank merged cells.
- A continuation page's first row containing only an order-number fragment and blank quantity completes the preceding page's trailing PB fragment, including a split suffix; it is not a product row. Concatenate the fragments; if still incomplete, accept only one unique prefix/suffix match in that FH's header order list. Apply the repaired order to the pending preceding row or inherit it for the next row, then validate against the header list. Stop if the fragment is missing, ambiguous, or unresolved when the FH ends.
- SKC: `供应商货号`, not the long `sz...` value in `SKC`. Color: `颜色/尺码`, not the parenthetical supplier color. Quantity: `实发数量`.

## SHEIN 旧版发货单

Signature: `发货单`, `订单号`, `平台SKC/商家货号`, `平台SKU`, `属性集`, `数量`.

- Date: `送货时间`; fall back to `确认提交时间` only when needed.
- Order: complete row-level PB in `订单号`. SKC: YY code in `平台SKC/商家货号` or its immediately following continuation row; ignore the long `sz...` identifier.
- Color: `属性集`. Quantity: row-level `数量`. Process every order in every FH/page, including merchant-goods continuation rows.

## TK/POCY 拣货单

Signature: `订单号: POCY...`, `下单时间`, `SKU货号`, `下单数量`.

- Process every POCY block on every page; use its POCY order number and `下单时间`, not `要求发货时间`.
- SKC: `SKU货号`/`货号`; repair split `N` + `QL`. Color: `产品信息` → `颜色:`.
- Sum `下单数量` size rows or use its `合计`; reconcile available details and total without double-counting. Ignore `未发货`, `待揽收`, and empty `拣货数`.

## TEMU 备货拣货单

Signature: `SKC货号`, `备货单号`, `属性集`, `数量`.

- Process every numbered product group on every page. Date: `打印时间`, not `创建时间` or `要求发货时间`.
- Require `备货单号` (`WB...`); never substitute `备货母单号` (`WP...`).
- SKC: `SKC货号`/`SKU货号`, not numeric `SKC` or `SKU ID`. Color: `属性集`. Quantity: `数量`, not `拣货数`.
- Sum size rows and reconcile each group's `合计`.
