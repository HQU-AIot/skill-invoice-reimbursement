#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse Chinese e-invoice PDFs and validate arithmetic.

Usage:
    python parse_invoice.py invoice.pdf
    python parse_invoice.py 01_电子发票/*.pdf --json invoices.json
    python parse_invoice.py invoice.pdf --buyer-tax-id 91110000XXXXXXXXXX

Handles the two common layouts:
  1) 价税合计(大写) 壹拾柒圆玖角 (小写) ¥17.90
  2) 价税合计（大写） （小写） ... 叁拾贰圆玖角伍分 ¥32.95

Exit code: 0 if all parsed invoices pass; 1 if any needs manual review.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

INVOICE_NO_LENGTHS = (8, 10, 12, 20)  # 老票 8/10/12 位，数电票 20 位
DIGITS = {"零": 0, "壹": 1, "贰": 2, "叁": 3, "肆": 4,
          "伍": 5, "陆": 6, "柒": 7, "捌": 8, "玖": 9}
UNITS = {"拾": 10, "佰": 100, "仟": 1000}
BIG = {"万": 10_000, "亿": 100_000_000}


def cn_to_number(s: str) -> float:
    """Convert Chinese financial numeral to float. '壹拾柒圆玖角' -> 17.9"""
    total = 0.0
    section = 0.0
    number = 0.0
    for ch in s:
        if ch in DIGITS:
            number = DIGITS[ch]
        elif ch in UNITS:
            if number == 0:
                number = 1
            section += number * UNITS[ch]
            number = 0
        elif ch in BIG:
            section = (section + number) * BIG[ch]
            total += section
            section = 0
            number = 0
        elif ch in "圆元":
            total += section + number
            section = 0
            number = 0
        elif ch == "角":
            total += number * 0.1
            number = 0
        elif ch == "分":
            total += number * 0.01
            number = 0
        elif ch == "整":
            pass
    return round(total + section + number, 2)


def _extract_text(pdf_path: Path) -> str:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is required: pip install pdfplumber")
    with pdfplumber.open(str(pdf_path)) as doc:
        return "\n".join((page.extract_text() or "") for page in doc.pages)


def _find_total(text: str) -> tuple[float | None, str]:
    """Return (total, uppercase_text)."""
    # Layout A: (大写) 壹拾柒圆玖角 (小写) ¥xx.xx
    m = re.search(
        r"价税合计\s*[（(]\s*大写\s*[)）]\s*([零壹贰叁肆伍陆柒捌玖拾佰仟万亿圆元角分整]{2,})"
        r".{0,80}?[（(]\s*小写\s*[)）]\s*[¥￥]?\s*([0-9]+(?:\.[0-9]+)?)",
        text, re.S)
    if m:
        return float(m.group(2)), m.group(1)
    # Layout B: find Chinese uppercase amount, then a ¥ amount equal to it
    cn_candidates = re.findall(r"[零壹贰叁肆伍陆柒捌玖拾佰仟万亿圆元角分整]{4,}", text)
    amounts = [float(x) for x in re.findall(r"[¥￥]\s*([0-9]+(?:\.[0-9]+)?)", text)]
    for cn in cn_candidates:
        try:
            value = cn_to_number(cn)
        except Exception:
            continue
        if value <= 0:
            continue
        if any(abs(a - value) < 0.005 for a in amounts):
            return value, cn
    return None, (cn_candidates[0] if cn_candidates else "")


def _find_amount_tax(text: str, total: float | None) -> tuple[float | None, float | None]:
    m = re.search(r"合\s*计\s*[¥￥]\s*([0-9]+(?:\.[0-9]+)?)\s*[¥￥]\s*([0-9]+(?:\.[0-9]+)?)", text)
    if m:
        return float(m.group(1)), float(m.group(2))
    if total is None:
        return None, None
    amounts = [float(x) for x in re.findall(r"[¥￥]\s*([0-9]+(?:\.[0-9]+)?)", text)]
    seen = set()
    for i, a in enumerate(amounts):
        for j, b in enumerate(amounts):
            if i == j or (i, j) in seen:
                continue
            seen.add((i, j))
            if abs(a + b - total) < 0.005:
                return max(a, b), min(a, b)
    return None, None


def parse_pdf(path: Path, expected_tax_id: str | None = None,
              expected_buyer_name: str | None = None) -> dict:
    text = _extract_text(path)
    flat = re.sub(r"[ \t]+", " ", text)

    invoice_no = None
    m = re.search(r"发票号码\s*[：:]\s*(\d{8,20})", flat)
    if m:
        invoice_no = m.group(1)
    if not invoice_no:
        # layout B: number on its own line (8/10/12/20 digits)
        m = re.search(r"(?m)^\s*(\d{8}|\d{10}|\d{12}|\d{20})\s*$", flat)
        if m:
            invoice_no = m.group(1)

    date = None
    m = re.search(r"开票日期\s*[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", flat)
    if not m:
        # layout B: date on its own line
        m = re.search(r"(?m)^\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*$", flat)
    if m:
        date = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    total, total_cn = _find_total(flat)
    amount, tax = _find_amount_tax(flat, total)

    names = re.findall(r"名称\s*[：:]\s*([^\s]{2,40})", flat)
    if expected_buyer_name and expected_buyer_name in flat:
        buyer = expected_buyer_name
    else:
        buyer = names[0] if names else ""
    others = [n for n in names if n != buyer]
    seller = others[0] if others else ""

    tax_ids = [t for t in re.findall(r"\b([0-9A-Z]{15,20})\b", flat) if t != invoice_no]
    buyer_tax = ""
    if expected_tax_id and expected_tax_id in flat:
        buyer_tax = expected_tax_id
    elif tax_ids:
        buyer_tax = tax_ids[0]

    checks = {
        "arithmetic": bool(amount is not None and tax is not None and total is not None
                           and abs(amount + tax - total) < 0.005),
        "uppercase": bool(total_cn and total is not None
                          and abs(cn_to_number(total_cn) - total) < 0.005),
        "invoice_no_format": bool(invoice_no and len(invoice_no) in INVOICE_NO_LENGTHS),
        "buyer_tax_id": bool(buyer_tax and (not expected_tax_id or buyer_tax == expected_tax_id)),
        "has_text": len(text.strip()) > 50,
    }
    if expected_buyer_name:
        checks["buyer_name"] = expected_buyer_name in flat
    needs_review = not all(checks.values())

    return {
        "file": str(path),
        "invoice_no": invoice_no,
        "date": date,
        "buyer": buyer,
        "buyer_tax_id": buyer_tax,
        "seller": seller,
        "amount": amount,
        "tax": tax,
        "total": total,
        "total_cn": total_cn,
        "checks": checks,
        "needs_manual_review": needs_review,
        "text_chars": len(text.strip()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse and validate Chinese e-invoice PDFs")
    ap.add_argument("files", nargs="+", help="PDF files")
    ap.add_argument("--json", help="write JSON result to this path")
    ap.add_argument("--buyer-tax-id", default="", help="expected buyer tax ID, e.g. 91110000XXXXXXXXXX")
    ap.add_argument("--buyer-name", default="", help="expected buyer name, e.g. 示例单位")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    results = []
    for f in args.files:
        p = Path(f)
        try:
            results.append(parse_pdf(p, args.buyer_tax_id or None, args.buyer_name or None))
        except Exception as exc:
            results.append({"file": str(p), "error": str(exc), "needs_manual_review": True})

    payload = {"count": len(results), "results": results}
    if args.json:
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.quiet:
        for r in results:
            if "error" in r:
                print(f"[ERROR] {r['file']}: {r['error']}")
                continue
            flag = "REVIEW" if r["needs_manual_review"] else "OK"
            print(f"[{flag}] {Path(r['file']).name} | {r['invoice_no']} | {r['date']} | "
                  f"¥{r['total']} | {r['buyer']} | {r['buyer_tax_id']}")
        bad = sum(1 for r in results if r.get("needs_manual_review"))
        print(f"\n{len(results)} invoices, {bad} need manual review")

    return 1 if any(r.get("needs_manual_review") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
