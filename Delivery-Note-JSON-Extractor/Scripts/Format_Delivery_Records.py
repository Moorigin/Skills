#!/usr/bin/env python3
"""Convert extracted delivery-note JSON into spreadsheet-ready records."""

from __future__ import annotations

import argparse
import json
import re
import sys
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


def main(output: str) -> dict[str, str]:
    if not output:
        return {"result": "[]"}

    clean_json = strip_markdown_json(output)

    try:
        data = json.loads(clean_json)
    except Exception:
        return {"result": "[]"}

    delivery_date = data.get("delivery_date")
    items = data.get("items", [])
    if not isinstance(items, list):
        return {"result": "[]"}

    grouped_records: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        order_number = item.get("order_number")
        if order_number is None:
            order_number = ""
        order_key = str(order_number).strip()
        quantity = parse_quantity(item.get("quantity", 0))

        if order_key in grouped_records:
            grouped_records[order_key]["数量"] += quantity
        else:
            grouped_records[order_key] = {
                "交付日期": delivery_date,
                "订单号": order_key,
                "平台SKC": item.get("platform_skc"),
                "属性集": item.get("attribute_set"),
                "数量": quantity,
            }

    formatted_records = list(grouped_records.values())
    return {"result": json.dumps(formatted_records, ensure_ascii=False)}


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
