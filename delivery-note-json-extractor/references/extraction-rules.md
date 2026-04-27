# Delivery Note Extraction Rules

Use these rules when extracting from raw PDF text.

Return exactly this JSON object and no surrounding prose:

```
{
  "delivery_date": "string",
  "items": [
    {
      "order_number": "string",
      "platform_skc": "string",
      "attribute_set": "string",
      "quantity": "number"
    }
  ]
} 
```

Field rules:

- delivery_date: Normalize the delivery date to YYYY-MM-DD. Use null or "" when absent.
- order_number: Extract order numbers from delivery-note item rows. Ignore unrelated text such as merchant name. Deduplicate by order number in the final item list when possible.
- platform_skc: Extract only the digits between YY and one of NQL, L, CSX, or CSP.
  - sz2412274638218934 2412YY059NQL -> 059
  - sz2406242981144480 ZXYY2406003L -> 2406003
  - sz25030754837937587 B2YY251325CSX -> 251325
  - sz260104113776879000549 RX12YY6606125CSP -> 6606125
- attribute_set: Output only the color string. Remove size and trailing codes such as -M.
  - 桃花粉拼JC076咖啡 -> 桃花粉拼咖啡
  - Remove embedded style/color codes such as JC209, JC076, spaces, brackets, and punctuation.
- quantity: Convert to a number. If the same order number appears multiple times, sum all quantities for that order.

Item handling:

- Treat every product/service line under the PDF's item/project section as a candidate item.
- Include discount rows only if they have an actual order number and quantity. Do not invent product fields from discount-only rows.
- If a requested field does not exist, use null or "".

Recommended extraction patterns:

- Platform SKC: YY(\d+?)(?:NQL|CSX|CSP|L)
- Remove attribute-set codes: remove [A-Z]{1,4}\d+, ASCII/full-width brackets, punctuation, whitespace, and trailing size markers like -M, -L, -XL, -均码.
- Prefer item rows containing order-like IDs and quantity columns over header/footer text.
