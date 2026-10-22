# 详细操作流程

本文按“一次完整整理”的顺序展开，可作为执行清单逐项打勾。

---

## 阶段 0：清点与备份

```bash
# 在项目目录内执行；先复制到同级目录，再移入项目，避免“复制进自己”
cd ..
cp -r 发票汇总 "发票汇总_备份_tmp"
mv "发票汇总_备份_tmp" "发票汇总/_原始备份_$(date +%Y%m%d)"
cd 发票汇总
```

不要使用 `cp -r . _原始备份_xxx`：目标在源目录内部，会报 “cannot copy a directory into itself”，并留下空目录。

统计输入：

```bash
find . -maxdepth 2 -type f | wc -l
find . -type f \( -iname '*.pdf' -o -iname '*.ofd' -o -iname '*.xml' \) | wc -l
find . -type f \( -iname '*.jpg' -o -iname '*.png' -o -iname '*.jpeg' \) | wc -l
```

把新文件统一放进三个入口：

```text
03_新增待整理/电子发票/
03_新增待整理/订单截图/
03_新增待整理/支付截图/
```

ZIP 包（嘉立创、立创等）先解压到临时目录，解压后保留原 zip 到 `99_其他/原始压缩包/`。

如果订单/支付截图来自 QQ、微信等聊天工具，直接从聊天图片缓存目录按时间批量复制到 `03_新增待整理`，不要逐张“另存为”；复制后按订单号/金额重命名，避免缓存文件名无意义。

---

## 阶段 1：解析发票

### 1.1 PDF

```python
import pdfplumber
with pdfplumber.open(path) as doc:
    text = "\n".join((p.extract_text() or "") for p in doc.pages)
```

需要提取的字段：

- 发票号码（数电票 20 位；老版电子票常见 8/10/12 位）
- 开票日期
- 购买方名称、税号
- 销售方名称、税号
- 明细：项目、规格、单位、数量、单价、金额、税率、税额
- 合计金额、合计税额、价税合计（大写/小写）
- 备注（常含订单号）
- 开票人

不要假设版式固定。至少见过两种：

1. **常规版式**：`价税合计(大写) 壹拾柒圆玖角 (小写) ¥17.90`
2. **标签/数值分离版式**：`价税合计（大写） （小写）` 在前，数值 `叁拾贰圆玖角伍分 ¥32.95` 在页面后部

`scripts/parse_invoice.py` 已兼容两种（用中文大写金额反查小写）。

### 1.2 OFD

```bash
pip install easyofd
```

```python
from easyofd import OFD
ofd = OFD()
ofd.read("发票.ofd", fmt="path")   # 必须指定 fmt="path"
pdf_bytes = ofd.to_pdf()
open("发票_OFD转PDF.pdf", "wb").write(pdf_bytes)
```

注意事项：

- `read()` 默认按 base64 处理，传路径会报 `UnicodeEncodeError`/`base64` 错误，必须 `fmt="path"`。
- 转换件的文字层可能把税号数字拆成空格（`1 2 1 0...`），**不要用它替代平台下载的正式 PDF**，只作为 OFD 原件的可视化副本。
- 转换后核对发票号、金额、购方名称三项。

### 1.3 XML

税务 XML 结构示例：

```xml
<EInvoice>
  <EInvoiceData>
    <SellerInformation><SellerName>...</SellerName><SellerIdNum>...</SellerIdNum></SellerInformation>
    <BuyerInformation><BuyerName>...</BuyerName><BuyerIdNum>...</BuyerIdNum></BuyerInformation>
    <BasicInformation>
      <TotalAmWithoutTax>124.99</TotalAmWithoutTax>
      <TotalTaxAm>16.25</TotalTaxAm>
      <TotalTax-includedAmount>141.24</TotalTax-includedAmount>
      <TotalTax-includedAmountInChinese>壹佰肆拾壹圆贰角肆分</TotalTax-includedAmountInChinese>
    </BasicInformation>
    <IssuItemInformation>...</IssuItemInformation>
  </EInvoiceData>
</EInvoice>
```

XML 不是发票版面，转 PDF 只能生成“信息页”。信息页必须标注“非发票原件”，不能当发票提交。

### 1.4 图片发票/截图

用视觉读取时逐项记录，不要只看总额：

- 发票号码（位数是否符合票种：数电票 20 位，老票 8/10/12 位）
- 购买方名称 + 税号（税号栏是否为空）
- 价税合计、金额、税额
- 销售方
- 发票类型（普票/专票）
- 备注/订单号

截图上常见陷阱：

- 暗色模式，金额小数位容易看错。
- 发票预览写“发票号码：以实物为准” → 不是正式发票。
- 购方只写“示例单位”，税号栏空白 → 发票不合规。

---

## 阶段 2：逐张校验

对每张发票跑 `scripts/parse_invoice.py`。脚本输出为 `{"count": N, "results": [...]}`，下面是 `results` 中一项的示例（传入 `--buyer-name` 时 `checks` 会多一个 `buyer_name`；不传则没有）：

```json
{
  "file": "01_电子发票/01_电子元件A_13.25元_发票12345678901234567890.pdf",
  "invoice_no": "12345678901234567890",
  "date": "2026-01-15",
  "buyer": "示例单位",
  "buyer_tax_id": "91110000XXXXXXXXXX",
  "seller": "示例电子科技有限公司",
  "amount": 11.73,
  "tax": 1.52,
  "total": 13.25,
  "total_cn": "壹拾叁圆贰角伍分",
  "checks": {
    "arithmetic": true,
    "uppercase": true,
    "invoice_no_format": true,
    "buyer_tax_id": true,
    "has_text": true,
    "buyer_name": true
  },
  "needs_manual_review": false
}
```

判定：

- 任意 check 为 false → `needs_manual_review=true`，人工看。
- `text_chars` 很少或为 0 → 图片型 PDF，转视觉读取。
- 校验通过才进入匹配阶段。

---

## 阶段 3：匹配订单与支付

### 3.1 订单截图要读的字段

- 订单编号（淘宝/天猫通常 19 位数字；拼多多带 `-`；立创 `SO...`；嘉立创 `平台自定义单号`）
- 下单时间
- 商品名称、规格、数量
- 商品总价、运费、优惠、实付
- 订单状态（已发货/已完成/已取消/已退款）
- 开票信息

### 3.2 支付截图要读的字段

- 支付时间
- 金额
- 支付方式（零钱/花呗/银行卡）
- 收款方/商户全称
- 交易单号/商户单号
- 状态（支付成功/已退款）

### 3.3 匹配顺序

1. 用发票备注里的订单号直接找订单。
2. 用金额 + 日期在订单截图里找。
3. 用金额 + 日期 + 收款方在支付截图里找。
4. 同一金额多笔时，用订单号/交易单号排除。

### 3.4 数量/规格核对

逐项对比发票明细与订单商品清单：

- 数量：发票 2 片 vs 订单 2 片。
- 单位：发票“套” vs 订单“个”属于单位差异，金额一致时可备注说明。
- 规格：发票“v1 10 片” vs 订单“2.0 5 片”属于不一致，必须确认或重开。

---

## 阶段 4：分类与隔离

对每个物品建立状态：

```text
complete        发票+订单+支付+金额一致+数量规格一致 → 报销表
amount_mismatch 发票金额 ≠ 实付 → 待补
spec_mismatch   规格/数量不一致 → 待补
no_order        缺订单 → 待补
no_payment      缺支付 → 待补
no_proof        订单支付都缺 → 待补
invalid_invoice 预览/缺税号/抬头错 → 待补
canceled        订单已取消 → 04_已取消订单
excluded        用户明确不报 → 99_其他/不报销
extra_payment   无对应发票的支付 → 03_待确认
```

待补文件夹内容：

```text
04_未报销发票_待补材料/01_物品_金额/
├─ 发票.pdf
├─ 订单截图.png
├─ 支付截图.jpg
└─ 缺什么.txt
```

`缺什么.txt` 模板：

```text
是什么：物品名称、数量
金额：xx.xx 元
发票号：xxxxxxxxxxxxxxxxxxxx
开票日期：2026-xx-xx
销售方：xxx
订单号：xxx

已有（都在本文件夹）：
- 发票.pdf
- 订单截图.png
- 支付截图.jpg

缺什么：xxx
说明：xxx
怎么补：xxx
状态：已从报销表剔除，补齐后即可入表。
```

---

## 阶段 5：编号与重命名

### 5.1 先定最终序号

按物品类别或原顺序排，输出 `old_idx -> seq` 映射。最终必须是 `1..N` 连续。

### 5.2 两阶段重命名

```python
tmp = []
for old, new in mapping.items():
    for p in root.glob(f"{old:02d}_*"):
        t = p.with_name("TMPRENAME_" + p.name)
        p.rename(t); tmp.append((t, new, p.name))
for t, new, old_name in tmp:
    rest = old_name.split("_", 1)[1]
    t.rename(t.with_name(f"{new:02d}_{rest}"))
```

### 5.3 同步数据源

如果数据存在 `data.py`/`manifest.json`，把所有文件路径前缀一起改掉，并跑一次：

```bash
python -c "import data; print(len(data.ITEMS))"
```

---

## 阶段 6：生成工作簿

默认极简版（推荐）：

- 只有一张 `报销明细`。
- 五列：序号、物品、用途、数量、价格。
- N 行 + 合计行。
- 无备注列、无说明行、无待补表。
- 合计 = `sum(amount)`。

Excel 锁文件处理：

```python
# 先存临时文件
wb.save("财务报表_更新.xlsx")
# 校验通过后，如果主文件被 Excel 打开：
# 1) 检查是否有未保存修改
# 2) 有修改先 SaveCopyAs 备份
# 3) Close(SaveChanges=False)
# 4) shutil.copy2 覆盖
# 5) 重新打开
```

---

## 阶段 7：生成文本报告

统一 UTF-8 with BOM、CRLF：

```python
Path("发票核对报告.txt").write_text("\r\n".join(lines), encoding="utf-8-sig", newline="")
```

报告结构建议：

1. TL;DR：张数、总额、可报销金额、待补数量。
2. 排除项（用户明确不报）。
3. 分批核对表。
4. 问题清单 P1..Pn（金额不一致、缺材料、重复、待确认、取消订单）。
5. 全量逐张核对表。
6. 检查方法与未做的检查。
7. 目录结构、命名规则、工作簿说明。
8. 建议处理顺序。
9. 附件索引。
10. 支付凭证核对表。

所有数字从数据计算，不手写。

---

## 阶段 8：交付文件夹

```text
报销交付_YYYYMMDD/
├─ 01-物品-发票.pdf
├─ 01-物品-详情.png
├─ 01-物品-支付.jpg
├─ ...
├─ NN-物品-发票-OFD转换件.pdf   # 仅当有 OFD
├─ NN-物品-XML信息页.pdf        # 仅当有 XML
├─ 财务报表.xlsx
└─ 00-报销说明.txt
```

生成后：

```bash
ls | wc -l
# 发票数 = 支付数 = 物品数
```

---

## 阶段 9：终审

逐项打勾：

- [ ] 工作簿只有一张表，序号 1..N 连续。
- [ ] 合计 = 逐张 PDF 金额之和。
- [ ] 交付夹每个序号都有发票/详情/支付。
- [ ] 交付件与主档 MD5 一致。
- [ ] 交付夹工作簿 = 主档工作簿（MD5）。
- [ ] 报告里的张数/总额/待补金额与工作簿一致。
- [ ] 待补项仍在待补文件夹，未删除。
- [ ] 备份完整。
- [ ] 工作簿回读校验 0 问题：单表、行数、序号、合计、金额格式。
