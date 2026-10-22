# manifest.json 字段说明

manifest 是整条流水线的唯一数据源。工作簿、交付夹、报告都应从它生成，避免多处手改。

## 顶层

```json
{
  "root": "D:/path/to/发票汇总",
  "buyer": {"name": "示例单位", "tax_id": "91110000XXXXXXXXXX"},
  "items": [],
  "pending": [],
  "excluded": [],
  "delivery": {"folder": "报销交付_YYYYMMDD", "workbook": "财务报表.xlsx"}
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| root | 否 | 项目根目录；不填则默认 manifest 所在目录 |
| buyer.name | 是 | 单位名称，用于校验发票购方 |
| buyer.tax_id | 是 | 单位税号 |
| items | 是 | 已报销项目 |
| pending | 否 | 待补项目 |
| excluded | 否 | 明确不报销项目 |
| delivery | 否 | 交付夹配置 |

## items[]

```json
{
  "seq": 1,
  "short": "电子元件A",
  "item": "电子元件A",
  "purpose": "示例用途",
  "qty": 1,
  "amount": 13.25,
  "invoice_no": "12345678901234567890",
  "invoice_date": "2026-01-15",
  "seller": "示例电子科技有限公司",
  "order_no": "1234567890123456789",
  "order_amount": 13.25,
  "invoice_file": "01_电子发票/01_电子元件A_13.25元_发票12345678901234567890.pdf",
  "order_files": ["02_订单截图/01_电子元件A_订单13.25元_1234567890123456789.png"],
  "payment_file": "02_订单截图/支付凭证/01_电子元件A_支付13.25元_1234567890123456789.jpg",
  "status": "complete",
  "note": ""
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| seq | 是 | 最终连续序号，从 1 开始 |
| short | 是 | 文件名用短名 |
| item | 是 | 工作簿物品全名 |
| purpose | 是 | 用途分类 |
| qty | 是 | 数量 |
| amount | 是 | 发票价税合计 |
| invoice_no | 是 | 发票号码（数电票 20 位；老票 8/10/12 位） |
| invoice_date | 是 | 开票日期 `YYYY-MM-DD` |
| seller | 是 | 销售方 |
| order_no | 否 | 订单号；无订单填 `""` |
| order_amount | 否 | 订单实付；无订单填 `null` |
| invoice_file | 是 | 主档发票路径（相对项目根） |
| order_files | 是 | 订单截图路径数组，至少 1 个 |
| payment_file | 是 | 支付截图路径；`complete` 项必须非空且文件存在 |
| status | 是 | `complete` 才进报销表；其他状态仅保留在 manifest 中，不参与构建 |
| note | 否 | 备注，默认空 |
| extra_files | 否 | 额外附件数组，元素为 `{"path": "...", "suffix": "附件名"}`；用于 OFD 转换件、XML 信息页等 |

`extra_files` 示例：

```json
"extra_files": [
  {"path": "01_电子发票/OFD与XML/01_电子元件A_发票.ofd", "suffix": "发票-OFD原件"},
  {"path": "01_电子发票/OFD与XML/01_电子元件A_OFD转换件.pdf", "suffix": "发票-OFD转换件"}
]
```

## pending[]

```json
{
  "code": "01",
  "item": "测试仪器B",
  "amount": 199.00,
  "issue": "缺订单详情",
  "folder": "04_未报销发票_待补材料/01_测试仪器B_199.00元",
  "invoice_file": "...",
  "order_files": [],
  "payment_file": "..."
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| code | 是 | 待补编号 `01..M`，不占报销序号 |
| item | 是 | 物品 |
| amount | 是 | 发票金额 |
| issue | 是 | 缺什么/问题 |
| folder | 是 | 待补文件夹 |
| invoice_file | 否 | 发票（可能只有预览） |
| order_files | 否 | 订单截图 |
| payment_file | 否 | 支付截图 |

## excluded[]

```json
{"item": "云服务费", "amount": 500.00, "reason": "按要求不报销", "file": "99_其他/不报销/..."}
```

## 校验建议

- `seq` 必须唯一且连续，且只对 `status=complete` 的条目编号。
- `amount > 0`。
- `status=complete` 时 `order_amount` 必须等于 `amount`。
- 所有文件路径必须存在，且必须是文件而不是目录。
- `invoice_no` 位数必须符合票种，且在同一批内唯一。
- `payment_file` 为空或指向目录时，`build_delivery.py` 应报错而不是崩溃（发布版已加固）。
- 修改 manifest 后重新构建交付夹；不要手工修改交付夹内的文件。
