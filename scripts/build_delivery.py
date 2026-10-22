#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a flat delivery folder from manifest.json.

Naming:
    {seq:02d}-{short}-发票{ext}
    {seq:02d}-{short}-详情{ext}
    {seq:02d}-{short}-详情2{ext}
    {seq:02d}-{short}-支付{ext}
    {seq:02d}-{short}-{extra_suffix}{ext}

Usage:
    python build_delivery.py --manifest manifest.json --out 报销交付_YYYYMMDD
    python build_delivery.py --manifest manifest.json --out out --workbook 财务报表.xlsx --force
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Build flat reimbursement delivery folder")
    ap.add_argument("--manifest", required=True, help="manifest.json")
    ap.add_argument("--out", required=True, help="output delivery folder")
    ap.add_argument("--root", help="project root (default: manifest directory)")
    ap.add_argument("--workbook", help="workbook to copy into the delivery folder")
    ap.add_argument("--force", action="store_true", help="remove existing output folder first")
    args = ap.parse_args()

    manifest_path = Path(args.manifest).resolve()
    data = load_manifest(manifest_path)
    if args.root:
        root = Path(args.root).resolve()
    else:
        root = Path(data.get("root") or manifest_path.parent).resolve()
    out = Path(args.out).resolve()

    if out.exists():
        if not args.force:
            print(f"ERROR: output exists: {out} (use --force to rebuild)", file=sys.stderr)
            return 2
        shutil.rmtree(out)
    out.mkdir(parents=True)

    items = [i for i in data.get("items", []) if i.get("status", "complete") == "complete"]
    items.sort(key=lambda x: int(x["seq"]))

    seqs = [int(i["seq"]) for i in items]
    expected = list(range(1, len(items) + 1))
    if seqs != expected:
        print(f"ERROR: seq is not contiguous 1..{len(items)}: {seqs}", file=sys.stderr)
        return 2

    problems = []
    counts = {"invoice": 0, "detail": 0, "payment": 0, "extra": 0}

    for it in items:
        seq = int(it["seq"])
        short = it["short"]
        base = f"{seq:02d}-{short}"

        inv_rel = it.get("invoice_file") or ""
        inv = root / inv_rel if inv_rel else None
        if inv is None or not inv.is_file():
            problems.append(f"{seq:02d} missing invoice: {inv_rel or '(empty)'}")
        else:
            dst = out / f"{base}-发票{inv.suffix.lower()}"
            shutil.copy2(inv, dst)
            counts["invoice"] += 1

        orders = [root / p for p in (it.get("order_files") or []) if p]
        if not orders:
            problems.append(f"{seq:02d} no order screenshot")
        for n, src in enumerate(orders, 1):
            if not src.is_file():
                problems.append(f"{seq:02d} missing order: {src}")
                continue
            suffix = "" if n == 1 else str(n)
            dst = out / f"{base}-详情{suffix}{src.suffix.lower()}"
            shutil.copy2(src, dst)
            counts["detail"] += 1

        pay_rel = it.get("payment_file") or ""
        pay = root / pay_rel if pay_rel else None
        if pay is None or not pay.is_file():
            problems.append(f"{seq:02d} missing payment: {pay_rel or '(empty)'}")
        else:
            dst = out / f"{base}-支付{pay.suffix.lower()}"
            shutil.copy2(pay, dst)
            counts["payment"] += 1

        for extra in it.get("extra_files", []):
            extra_rel = extra.get("path") or ""
            src = root / extra_rel if extra_rel else None
            if src is None or not src.is_file():
                problems.append(f"{seq:02d} missing extra: {extra_rel or '(empty)'}")
                continue
            suffix = extra.get("suffix", "附件")
            dst = out / f"{base}-{suffix}{src.suffix.lower()}"
            shutil.copy2(src, dst)
            counts["extra"] += 1

    if args.workbook:
        wb = Path(args.workbook)
        if not wb.is_absolute():
            wb = root / wb
        if wb.is_file():
            shutil.copy2(wb, out / wb.name)
        else:
            problems.append(f"missing workbook: {wb}")

    print(f"built {out}")
    print(f"items={len(items)} invoice={counts['invoice']} detail={counts['detail']} "
          f"payment={counts['payment']} extra={counts['extra']}")
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  -", p)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
