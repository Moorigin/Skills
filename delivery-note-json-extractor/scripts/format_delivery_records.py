#!/usr/bin/env python3
"""Convert extracted delivery-note JSON into spreadsheet-ready records."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from typing import Any


def strip_markdown_json(output: str) -> str:
    text = output.strip()
    text = re.sub(r"^```[\w-]*\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_quantity(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def clean_string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def main(output: str) -> dict[str, str]:
    if not output:
        return {"result": "[]"}

    clean_json = strip_markdown_json(output)
    try:
        data = json.loads(clean_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"result": "[]"}

    if not isinstance(data, dict):
        return {"result": "[]"}
    delivery_date = data.get("delivery_date")
    items = data.get("items", [])
    if not isinstance(items, list):
        return {"result": "[]"}

    grouped_records: OrderedDict[tuple[str, str, str] | tuple[str, int], dict[str, Any]] = OrderedDict()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        order_number = clean_string(item.get("order_number"))
        platform_skc = clean_string(item.get("platform_skc"))
        attribute_set = clean_string(item.get("attribute_set"))
        quantity = parse_quantity(item.get("quantity", 0))
        if quantity == 0:
            continue

        # Never merge unrelated records merely because both order numbers are missing.
        key: tuple[str, str, str] | tuple[str, int]
        if order_number:
            key = (order_number, platform_skc, attribute_set)
        else:
            key = ("__missing_order__", index)

        if key in grouped_records:
            grouped_records[key]["数量"] += quantity
        else:
            grouped_records[key] = {
                "交付日期": delivery_date,
                "订单号": order_number,
                "平台SKC": platform_skc,
                "属性集": attribute_set,
                "数量": quantity,
            }

    return {"result": json.dumps(list(grouped_records.values()), ensure_ascii=False)}


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="Path to extracted JSON. Reads stdin if omitted.")
    parser.add_argument("--output", "-o", help="Write result object to this JSON file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the outer result JSON.")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as handle:
            raw = handle.read()
    else:
        raw = sys.stdin.read()

    result = main(raw)
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
