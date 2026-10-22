#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the invoice-reimbursement scripts.

Run:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from parse_invoice import cn_to_number  # noqa: E402


def run_script(name: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=60,
    )


def make_item(seq: int, amount: float, invoice_no: str) -> dict:
    return {
        "seq": seq,
        "short": f"物品{seq}",
        "item": f"物品{seq}",
        "purpose": "测试",
        "qty": 1,
        "amount": amount,
        "invoice_no": invoice_no,
        "invoice_date": "2026-01-15",
        "seller": "测试商家",
        "order_no": f"SO{seq}",
        "order_amount": amount,
        "invoice_file": f"inv/{seq}.pdf",
        "order_files": [f"ord/{seq}.png"],
        "payment_file": f"pay/{seq}.jpg",
        "status": "complete",
        "note": "",
    }


def write_manifest(root: Path, items: list[dict]) -> Path:
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps({"root": str(root).replace("\\", "/"), "items": items},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


class TestChineseAmount(unittest.TestCase):
    def test_common_amounts(self):
        cases = {
            "壹拾柒圆玖角": 17.90,
            "壹拾捌圆玖角": 18.90,
            "叁拾贰圆玖角伍分": 32.95,
            "壹佰肆拾壹圆贰角肆分": 141.24,
            "壹万贰仟叁佰肆拾伍圆陆角柒分": 12345.67,
            "壹亿贰仟万圆整": 120000000.0,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertAlmostEqual(cn_to_number(text), expected, places=2)


class TestBuildDelivery(unittest.TestCase):
    def test_empty_payment_reports_problem_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "inv").mkdir()
            (root / "ord").mkdir()
            (root / "inv" / "1.pdf").write_bytes(b"%PDF-1.4\n%fake\n")
            (root / "ord" / "1.png").write_bytes(b"fake image")

            item = make_item(1, 10.0, "12345678901234567890")
            item["payment_file"] = ""
            manifest = write_manifest(root, [item])
            out = root / "out"

            proc = run_script("build_delivery.py", "--manifest", str(manifest), "--out", str(out))
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("missing payment", proc.stdout)
            self.assertIn("(empty)", proc.stdout)
            self.assertNotIn("Traceback", proc.stderr)


class TestCheckDelivery(unittest.TestCase):
    def _build_two_items(self, root: Path) -> tuple[Path, Path]:
        (root / "inv").mkdir()
        (root / "ord").mkdir()
        (root / "pay").mkdir()
        items = []
        for seq, amount in ((1, 10.0), (2, 20.5)):
            (root / "inv" / f"{seq}.pdf").write_bytes(b"%PDF-1.4\n%fake\n")
            (root / "ord" / f"{seq}.png").write_bytes(f"order {seq}".encode())
            (root / "pay" / f"{seq}.jpg").write_bytes(f"pay {seq}".encode())
            items.append(make_item(seq, amount, f"1234567890123456789{seq - 1}"))
        manifest = write_manifest(root, items)
        out = root / "out"
        proc = run_script(
            "build_delivery.py", "--manifest", str(manifest), "--out", str(out),
            "--workbook", str(root / "wb.xlsx"),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return manifest, out

    def _write_workbook(self, root: Path) -> Path:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "报销明细"
        ws.append(["序号", "物品", "用途", "数量", "价格"])
        ws.append(["01", "物品1", "测试", 1, 10.0])
        ws.append(["02", "物品2", "测试", 1, 20.5])
        ws.append(["合计", "2 张", "", "", 30.5])
        path = root / "wb.xlsx"
        wb.save(path)
        return path

    def test_text_seq_and_total_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            manifest, out = self._build_two_items(root)
            # Rebuild now that the workbook exists, so it is copied into the delivery.
            proc = run_script(
                "build_delivery.py", "--manifest", str(manifest), "--out", str(out),
                "--workbook", str(root / "wb.xlsx"), "--force",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            proc = run_script(
                "check_delivery.py", "--manifest", str(manifest), "--delivery", str(out),
                "--workbook", str(root / "wb.xlsx"),
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr + str(proc.args))
            self.assertIn("workbook data_rows=2 total=30.5", proc.stdout)

    def test_detail_count_mismatch_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            manifest, out = self._build_two_items(root)
            (out / "01-物品1-详情9.png").write_bytes(b"stale")

            proc = run_script(
                "check_delivery.py", "--manifest", str(manifest), "--delivery", str(out),
                "--workbook", str(root / "wb.xlsx"),
            )
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("detail count 2 != order_files 1", proc.stdout)


if __name__ == "__main__":
    unittest.main()
