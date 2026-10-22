#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find duplicate invoices/screenshots by MD5 and invoice number.

Read-only by default. With --apply --quarantine-dir DIR, moves all but the
first copy of each MD5 group into DIR (prefix "重复_").

Usage:
    python dedupe.py --root 发票汇总
    python dedupe.py --root . --json dup.json
    python dedupe.py --root . --apply --quarantine-dir 99_其他/重复发票
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

SUFFIXES = {".pdf", ".ofd", ".xml", ".jpg", ".jpeg", ".png"}
SKIP_DIRS = ("_原始备份", "报销交付", "99_其他/重复", "历史待办", "OFD与XML")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in SUFFIXES:
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if any(rel.startswith(s) or f"/{s}" in rel for s in SKIP_DIRS):
            continue
        yield p


def invoice_no_from_pdf(path: Path) -> str | None:
    try:
        import pdfplumber
    except ImportError:
        return None
    if path.suffix.lower() != ".pdf":
        return None
    try:
        with pdfplumber.open(str(path)) as doc:
            text = "\n".join((page.extract_text() or "") for page in doc.pages)
    except Exception:
        return None
    m = re.search(r"发票号码\s*[：:]\s*(\d{20})", text)
    if m:
        return m.group(1)
    m = re.search(r"(?m)^\s*(\d{20})\s*$", text)
    return m.group(1) if m else None


def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 2
    while True:
        candidate = dest.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Find duplicate invoices/screenshots")
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--json", help="write JSON report")
    ap.add_argument("--apply", action="store_true", help="move duplicates (requires --quarantine-dir)")
    ap.add_argument("--quarantine-dir", help="destination for duplicates")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    files = sorted(iter_files(root))

    by_md5: dict[str, list[Path]] = defaultdict(list)
    for p in files:
        by_md5[md5(p)].append(p)

    by_inv: dict[str, list[Path]] = defaultdict(list)
    for p in files:
        inv = invoice_no_from_pdf(p)
        if inv:
            by_inv[inv].append(p)

    dup_files = {h: [str(p.relative_to(root)) for p in ps]
                 for h, ps in by_md5.items() if len(ps) > 1}
    dup_invoices = {inv: [str(p.relative_to(root)) for p in ps]
                    for inv, ps in by_inv.items() if len(ps) > 1}

    report = {
        "root": str(root),
        "files_scanned": len(files),
        "duplicate_file_groups": len(dup_files),
        "duplicate_file_count": sum(len(v) - 1 for v in dup_files.values()),
        "duplicate_invoice_groups": len(dup_invoices),
        "duplicate_invoice_count": sum(len(v) - 1 for v in dup_invoices.values()),
        "duplicate_files": dup_files,
        "duplicate_invoices": dup_invoices,
    }

    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"scanned {len(files)} files")
    print(f"duplicate file groups: {len(dup_files)} ({report['duplicate_file_count']} extra copies)")
    for h, paths in dup_files.items():
        print(f"  MD5 {h[:10]}...")
        for p in paths:
            print(f"    {p}")
    print(f"duplicate invoice-number groups: {len(dup_invoices)} ({report['duplicate_invoice_count']} extra copies)")
    for inv, paths in dup_invoices.items():
        print(f"  {inv}")
        for p in paths:
            print(f"    {p}")

    if args.apply:
        if not args.quarantine_dir:
            print("ERROR: --apply requires --quarantine-dir", file=sys.stderr)
            return 2
        dest_dir = root / args.quarantine_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        for h, paths in dup_files.items():
            for rel in paths[1:]:
                src = root / rel
                dest = unique_dest(dest_dir / f"重复_{src.name}")
                shutil.move(str(src), str(dest))
                moved += 1
        print(f"moved {moved} duplicate files to {dest_dir}")
        if dup_invoices:
            print(f"NOTE: {len(dup_invoices)} invoice-number group(s) with different bytes were NOT moved.")
            print("      Review duplicate_invoices and quarantine them manually.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
