#!/usr/bin/env python3
"""Extract supported Chinese delivery-note PDFs into normalized JSON."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class ExtractionError(RuntimeError):
    """Raised when a PDF cannot be extracted without guessing."""


@dataclass
class PageData:
    text: str
    tables: list[list[list[str | None]]]


DATE_PATTERN = r"(?P<year>20\d{2})\s*[年./-]\s*(?P<month>\d{1,2})\s*(?:月|[./-])\s*(?P<day>\d{1,2})\s*日?"
SIZE_PATTERN = re.compile(
    r"(?i)(?:[-_/\s]+)?(?:XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|[3-9]XL|均码|FREE(?:SIZE)?|ONE\s*SIZE)$"
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).replace("\u00a0", " ")


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", normalize_text(value))


def normalized_header(value: Any) -> str:
    return compact(value).replace("⾊", "色").replace("⽚", "片")


def flex_label(label: str) -> str:
    return r"\s*".join(re.escape(char) for char in label)


def extract_dates_after_label(text: str, label: str) -> list[str]:
    pattern = re.compile(f"{flex_label(label)}\\s*[::]?\\s*{DATE_PATTERN}", re.IGNORECASE)
    dates: list[str] = []
    for match in pattern.finditer(normalize_text(text)):
        dates.append(
            f"{int(match.group('year')):04d}-{int(match.group('month')):02d}-{int(match.group('day')):02d}"
        )
    return dates


def choose_delivery_date(text: str, labels: Iterable[str]) -> str:
    for label in labels:
        values = list(OrderedDict.fromkeys(extract_dates_after_label(text, label)))
        if len(values) > 1:
            raise ExtractionError(f"字段“{label}”出现多个不同日期: {', '.join(values)}")
        if values:
            return values[0]
    fallback = re.search(DATE_PATTERN, normalize_text(text))
    if fallback:
        return (
            f"{int(fallback.group('year')):04d}-{int(fallback.group('month')):02d}-"
            f"{int(fallback.group('day')):02d}"
        )
    raise ExtractionError("未找到可用的交付日期")


def parse_quantity(value: Any) -> int | None:
    text = compact(value).replace(",", "")
    if not text:
        return None
    if not re.fullmatch(r"\d+(?:\.0+)?", text):
        return None
    return int(float(text))


def extract_platform_skc(value: Any) -> str:
    text = compact(value).upper()
    match = re.search(r"YY(\d+)", text)
    return match.group(1) if match else ""


def clean_attribute(value: Any) -> str:
    text = normalize_text(value).strip()
    previous = None
    while text != previous:
        previous = text
        text = SIZE_PATTERN.sub("", text).strip()
    text = re.sub(r"[A-Z]{1,4}\d+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\s\[\]【】(){}<>《》,，、;；:：]+", "", text)
    return text.strip("-_/|+")


def extract_prefixed_identifier(value: Any, prefix: str) -> str:
    match = re.search(rf"{re.escape(prefix)}\d{{8,}}", compact(value), re.IGNORECASE)
    return match.group(0).upper() if match else ""


def find_column(headers: list[str | None], *names: str) -> int | None:
    normalized = [normalized_header(header) for header in headers]
    for name in names:
        wanted = normalized_header(name)
        for index, header in enumerate(normalized):
            if header == wanted or wanted in header:
                return index
    return None


def cell(row: list[str | None], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return normalize_text(row[index])


def extract_shipment_number(value: Any) -> str:
    match = re.search(r"FH\d{10,}", compact(value), flags=re.IGNORECASE)
    return match.group(0).upper() if match else ""


def read_pdf(path: Path) -> list[PageData]:
    # Some supplier PDFs omit optional font metadata. pdfminer can still read
    # them correctly, so keep those non-actionable warnings out of stderr.
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    try:
        import pdfplumber
    except ImportError as exc:
        raise ExtractionError("缺少 pdfplumber; 请使用包含 PDF 依赖的 Python 环境") from exc

    pages: list[PageData] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                pages.append(
                    PageData(
                        text=normalize_text(page.extract_text(x_tolerance=2, y_tolerance=2) or ""),
                        tables=page.extract_tables() or [],
                    )
                )
    except Exception as exc:
        raise ExtractionError(f"无法读取 PDF: {exc}") from exc

    if not pages or not any(page.text.strip() or page.tables for page in pages):
        raise ExtractionError("PDF 没有可用文本层; 请先 OCR")
    return pages


def detect_layout(pages: list[PageData]) -> str:
    text = normalize_text("\n".join(page.text for page in pages))
    collapsed = compact(text)
    if all(token in collapsed for token in ("平台SKC/商家货号", "平台SKU", "属性集", "数量")):
        return "shein-delivery"
    if all(token in collapsed for token in ("供应商货号", "颜色/尺码", "实发数量")):
        return "shein-packing"
    if all(token in collapsed for token in ("备货母单号", "备货单号", "SKC货号", "属性集")):
        return "temu"
    if all(token in collapsed for token in ("订单号:POCY", "下单时间", "要求发货时间", "SKU货号")):
        return "tk"
    raise ExtractionError("未识别的发货单版式; 请渲染页面后按参考规则人工抽取")


def merge_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()
    for item in items:
        order = normalize_text(item.get("order_number")).strip()
        platform = normalize_text(item.get("platform_skc")).strip()
        attribute = clean_attribute(item.get("attribute_set"))
        quantity = parse_quantity(item.get("quantity"))
        if quantity is None:
            raise ExtractionError(f"订单 {order or '[空]'} 的数量无效")
        key = (order, platform, attribute)
        if key not in merged:
            merged[key] = {
                "order_number": order,
                "platform_skc": platform,
                "attribute_set": attribute,
                "quantity": quantity,
            }
        else:
            merged[key]["quantity"] += quantity
    return list(merged.values())


def validate_result(result: dict[str, Any]) -> None:
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", normalize_text(result.get("delivery_date"))):
        raise ExtractionError("交付日期未规范化")
    items = result.get("items")
    if not isinstance(items, list) or not items:
        raise ExtractionError("没有提取到商品记录")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ExtractionError(f"第 {index} 条记录不是对象")
        for field in ("order_number", "platform_skc", "attribute_set", "quantity"):
            if field not in item:
                raise ExtractionError(f"第 {index} 条记录缺少 {field}")
        if not item["order_number"]:
            raise ExtractionError(f"第 {index} 条记录缺少订单号")
        if not re.fullmatch(r"\d+", normalize_text(item["platform_skc"])):
            raise ExtractionError(f"第 {index} 条记录的平台 SKC 无效")
        if not item["attribute_set"]:
            raise ExtractionError(f"第 {index} 条记录缺少颜色属性")
        if not isinstance(item["quantity"], int) or item["quantity"] < 0:
            raise ExtractionError(f"第 {index} 条记录的数量无效")


def parse_tk(pages: list[PageData]) -> dict[str, Any]:
    all_text = "\n".join(page.text for page in pages)
    delivery_date = choose_delivery_date(all_text, ("要求发货时间", "发货时间"))
    items: list[dict[str, Any]] = []

    for page in pages:
        orders = re.findall(r"订单号\s*[:]\s*(POCY\d+)", normalize_text(page.text), flags=re.IGNORECASE)
        product_tables = []
        for table in page.tables:
            if not table:
                continue
            if find_column(table[0], "SKU货号") is not None and find_column(table[0], "下单数量") is not None:
                product_tables.append(table)
        if len(orders) != len(product_tables):
            raise ExtractionError(
                f"TK 页面中的订单头数量 ({len(orders)}) 与商品表数量 ({len(product_tables)}) 不一致"
            )

        for order, table in zip(orders, product_tables):
            headers = table[0]
            info_index = find_column(headers, "产品信息")
            sku_index = find_column(headers, "SKU货号")
            quantity_index = find_column(headers, "下单数量")
            info_text = "\n".join(cell(row, info_index) for row in table[1:] if cell(row, info_index))
            sku_text = "\n".join(cell(row, sku_index) for row in table[1:] if cell(row, sku_index))
            color_match = re.search(r"颜色\s*[:]\s*([^\s]+)", normalize_text(info_text))
            attribute = clean_attribute(color_match.group(1) if color_match else "")
            platform = extract_platform_skc(sku_text or info_text)

            detail_sum = 0
            total = None
            for row in table[1:]:
                if any(compact(value) == "合计" for value in row if value is not None):
                    total = parse_quantity(cell(row, quantity_index))
                    continue
                value = parse_quantity(cell(row, quantity_index))
                if value is not None:
                    detail_sum += value
            if total is not None and total != detail_sum:
                raise ExtractionError(f"TK 订单 {order} 的下单数量合计 {total} 与明细和 {detail_sum} 不一致")
            quantity = total if total is not None else detail_sum
            items.append(
                {
                    "order_number": order,
                    "platform_skc": platform,
                    "attribute_set": attribute,
                    "quantity": quantity,
                }
            )

    return {"delivery_date": delivery_date, "items": merge_items(items)}


def parse_temu(pages: list[PageData]) -> dict[str, Any]:
    all_text = "\n".join(page.text for page in pages)
    delivery_date = choose_delivery_date(all_text, ("要求发货时间", "发货时间"))
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def finish_current() -> None:
        nonlocal current
        if current is not None:
            groups.append(current)
            current = None

    for page in pages:
        for table in page.tables:
            if not table:
                continue
            headers = table[0]
            info_index = find_column(headers, "商品信息")
            attribute_index = find_column(headers, "属性集")
            sku_index = find_column(headers, "SKU货号")
            quantity_index = find_column(headers, "数量")
            if None in (info_index, attribute_index, sku_index, quantity_index):
                continue
            for row in table[1:]:
                info = cell(row, info_index)
                attribute = cell(row, attribute_index)
                if info and ("备货单号" in compact(info) or "备货母单号" in compact(info)):
                    finish_current()
                    current = {"info": info, "rows": [], "total": None}
                if current is None:
                    continue
                if compact(attribute) == "合计":
                    current["total"] = parse_quantity(cell(row, quantity_index))
                    finish_current()
                    continue
                quantity = parse_quantity(cell(row, quantity_index))
                if quantity is not None:
                    current["rows"].append(
                        {
                            "attribute": attribute,
                            "sku": cell(row, sku_index),
                            "quantity": quantity,
                        }
                    )
    finish_current()

    items: list[dict[str, Any]] = []
    for group in groups:
        info = normalize_text(group["info"])
        order_match = re.search(r"(?<!母)备货单号\s*[:]\s*(WB\d+)", info, flags=re.IGNORECASE)
        if not order_match:
            order_match = re.search(r"备货母单号\s*[:]\s*(WP\d+)", info, flags=re.IGNORECASE)
        order = order_match.group(1).upper() if order_match else ""
        detail_total = sum(row["quantity"] for row in group["rows"])
        if group["total"] is not None and group["total"] != detail_total:
            raise ExtractionError(f"TEMU 备货单 {order or '[空]'} 的合计 {group['total']} 与明细和 {detail_total} 不一致")

        buckets: OrderedDict[tuple[str, str], int] = OrderedDict()
        for row in group["rows"]:
            attribute = clean_attribute(row["attribute"])
            platform = extract_platform_skc(row["sku"] or info)
            key = (platform, attribute)
            buckets[key] = buckets.get(key, 0) + row["quantity"]
        for (platform, attribute), quantity in buckets.items():
            items.append(
                {
                    "order_number": order,
                    "platform_skc": platform,
                    "attribute_set": attribute,
                    "quantity": quantity,
                }
            )

    return {"delivery_date": delivery_date, "items": merge_items(items)}


def shein_header_orders(text: str) -> list[str]:
    collapsed = compact(text)
    match = re.search(r"SHEIN订单号(.*?)(?:快递公司|发货仓库)", collapsed, flags=re.IGNORECASE)
    source = match.group(1) if match else ""
    values = re.findall(r"PB\d{8,}", source, flags=re.IGNORECASE)
    return [value.upper() for value in OrderedDict.fromkeys(values)]


def validate_document_total(document: dict[str, Any], label: str) -> None:
    rows = document.get("rows", [])
    if not rows:
        raise ExtractionError(f"{label} {document['shipment']} 没有提取到明细")
    detail_total = sum(item["quantity"] for item in rows)
    printed_totals = list(OrderedDict.fromkeys(value for value in document.get("totals", []) if value is not None))
    if len(printed_totals) > 1:
        raise ExtractionError(
            f"{label} {document['shipment']} 出现多个不同合计: {', '.join(map(str, printed_totals))}"
        )
    if printed_totals and printed_totals[0] != detail_total:
        raise ExtractionError(
            f"{label} {document['shipment']} 的合计 {printed_totals[0]} 与跨页明细和 {detail_total} 不一致"
        )


def parse_shein_packing(pages: list[PageData]) -> dict[str, Any]:
    all_text = "\n".join(page.text for page in pages)
    delivery_date = choose_delivery_date(all_text, ("预约取件时间", "打印时间", "发货时间"))
    documents: OrderedDict[str, dict[str, Any]] = OrderedDict()
    current_shipment = ""
    found_table = False

    for page_number, page in enumerate(pages, start=1):
        shipment = extract_shipment_number(page.text) or current_shipment
        if not shipment:
            raise ExtractionError(f"SHEIN 配货单第 {page_number} 页缺少 FH 发货单号")
        current_shipment = shipment
        document = documents.setdefault(
            shipment,
            {
                "shipment": shipment,
                "header_orders": [],
                "rows": [],
                "totals": [],
                "last_order": "",
                "last_supplier": "",
            },
        )
        page_orders = shein_header_orders(page.text)
        for order in page_orders:
            if order not in document["header_orders"]:
                document["header_orders"].append(order)

        page_has_table = False
        for table in page.tables:
            if not table:
                continue
            headers = table[0]
            supplier_index = find_column(headers, "供应商货号")
            attribute_index = find_column(headers, "颜色/尺码", "颜色尺码")
            quantity_index = find_column(headers, "实发数量")
            if None in (supplier_index, attribute_index, quantity_index):
                continue
            found_table = True
            page_has_table = True
            order_index = find_column(headers, "订单号")

            for row in table[1:]:
                if any(compact(value) == "合计" for value in row if value is not None):
                    document["totals"].append(parse_quantity(cell(row, quantity_index)))
                    continue
                quantity = parse_quantity(cell(row, quantity_index))
                if quantity is None:
                    continue

                supplier = cell(row, supplier_index) or document["last_supplier"]
                if supplier:
                    document["last_supplier"] = supplier
                if order_index is not None:
                    order = extract_prefixed_identifier(cell(row, order_index), "PB") or document["last_order"]
                elif len(page_orders) == 1:
                    order = page_orders[0]
                elif len(document["header_orders"]) == 1:
                    order = document["header_orders"][0]
                else:
                    order = ""
                if order:
                    document["last_order"] = order

                document["rows"].append(
                    {
                        "order_number": order,
                        "platform_skc": extract_platform_skc(supplier),
                        "attribute_set": clean_attribute(cell(row, attribute_index)),
                        "quantity": quantity,
                    }
                )
        if not page_has_table:
            raise ExtractionError(f"SHEIN 配货单第 {page_number} 页没有找到明细表")

    if not found_table:
        raise ExtractionError("未找到 SHEIN 配货明细表")

    items: list[dict[str, Any]] = []
    for document in documents.values():
        validate_document_total(document, "SHEIN 配货单")
        header_orders = set(document["header_orders"])
        if header_orders:
            for item in document["rows"]:
                order = item["order_number"]
                if order and order not in header_orders:
                    raise ExtractionError(
                        f"SHEIN 配货单 {document['shipment']} 的行级订单号 {order} 不在页眉订单清单中"
                    )
        items.extend(document["rows"])
    return {"delivery_date": delivery_date, "items": merge_items(items)}


def parse_shein_delivery(pages: list[PageData]) -> dict[str, Any]:
    all_text = "\n".join(page.text for page in pages)
    delivery_date = choose_delivery_date(all_text, ("送货时间", "确认提交时间", "发货时间"))
    documents: OrderedDict[str, dict[str, Any]] = OrderedDict()
    current_shipment = ""
    found_table = False

    for page_number, page in enumerate(pages, start=1):
        shipment = extract_shipment_number(page.text) or current_shipment
        if not shipment:
            raise ExtractionError(f"SHEIN 发货单第 {page_number} 页缺少 FH 发货单号")
        current_shipment = shipment
        document = documents.setdefault(shipment, {"shipment": shipment, "rows": [], "totals": []})
        page_has_table = False

        for table in page.tables:
            if not table:
                continue
            headers = table[0]
            order_index = find_column(headers, "订单号")
            goods_index = find_column(headers, "平台SKC/商家货号")
            attribute_index = find_column(headers, "属性集")
            quantity_index = find_column(headers, "数量")
            if None in (order_index, goods_index, attribute_index, quantity_index):
                continue
            found_table = True
            page_has_table = True
            pending: dict[str, Any] | None = None

            def finish_pending() -> None:
                nonlocal pending
                if pending is None:
                    return
                if not pending["platform_skc"]:
                    raise ExtractionError(
                        f"SHEIN 发货单 {shipment} 的订单 {pending['order_number'] or '[空]'} 缺少 YY 商家货号"
                    )
                document["rows"].append(pending)
                pending = None

            for row in table[1:]:
                if any(compact(value) == "合计" for value in row if value is not None):
                    finish_pending()
                    document["totals"].append(parse_quantity(cell(row, quantity_index)))
                    continue

                order = extract_prefixed_identifier(cell(row, order_index), "PB")
                attribute = clean_attribute(cell(row, attribute_index))
                quantity = parse_quantity(cell(row, quantity_index))
                goods = cell(row, goods_index)
                platform = extract_platform_skc(goods)

                if order and attribute and quantity is not None:
                    finish_pending()
                    pending = {
                        "order_number": order,
                        "platform_skc": platform,
                        "attribute_set": attribute,
                        "quantity": quantity,
                    }
                    if platform:
                        finish_pending()
                elif pending is not None and platform:
                    pending["platform_skc"] = platform
                    finish_pending()
            finish_pending()

        if not page_has_table:
            raise ExtractionError(f"SHEIN 发货单第 {page_number} 页没有找到明细表")

    if not found_table:
        raise ExtractionError("未找到 SHEIN 发货明细表")

    items: list[dict[str, Any]] = []
    for document in documents.values():
        validate_document_total(document, "SHEIN 发货单")
        items.extend(document["rows"])
    return {"delivery_date": delivery_date, "items": merge_items(items)}


def extract_pdf(path: Path) -> tuple[str, dict[str, Any]]:
    pages = read_pdf(path)
    layout = detect_layout(pages)
    if layout == "shein-packing":
        result = parse_shein_packing(pages)
    elif layout == "shein-delivery":
        result = parse_shein_delivery(pages)
    elif layout == "tk":
        result = parse_tk(pages)
    else:
        result = parse_temu(pages)
    validate_result(result)
    return layout, result


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Path to the delivery-note PDF.")
    parser.add_argument("--output", "-o", help="Write raw extraction JSON to this path.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument(
        "--show-format",
        action="store_true",
        help="Print the detected layout name to stderr without changing the JSON contract.",
    )
    args = parser.parse_args()

    path = Path(args.input).expanduser().resolve()
    if not path.is_file():
        print(f"error: PDF 不存在: {path}", file=sys.stderr)
        return 2
    try:
        layout, result = extract_pdf(path)
    except ExtractionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.show_format:
        print(f"detected_format: {layout}", file=sys.stderr)
    output = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
