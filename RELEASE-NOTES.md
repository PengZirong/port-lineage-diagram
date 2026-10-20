# Port Lineage Diagram v1.0.0

端口式流程与字段血缘一体图 Skill 的首个版本。

## 本次发布

同一张图展示流程步骤、字段端口、透传、转换、查表、分支、汇合与外部来源。
默认案例为电商订单结算：价格与运费可独立计算，最终生成 5 个输出字段。
另附文件导入案例，验证模型与绘图逻辑不绑定特定业务字段。

## 使用

解压 `port-lineage-diagram-v1.0.0.zip`，保留目录结构；让 Agent 读取 `SKILL.md`，
或将整个 Skill 文件夹放入所用客户端支持的 skills 目录。

独立构建：

```bash
python3 scripts/lineage.py build examples/order-checkout.json --out output/checkout --strict
```

核心构建要求 Python 3.10+，无需第三方库；HTML 可离线打开。
PNG 验收脚本另需 Playwright 与本机 Chromium。

## 验证与限制

发布前重新运行 22 项单元测试以及两份示例的严格构建。
原始包附带订单示例 23 项、文件导入示例 21 项浏览器检查记录；
这些浏览器记录来自原版本构建，不代表每次发布都重跑了浏览器。

不自动从任意仓库采集血缘；不执行规则字符串；来源已定义不等于来源已由真实代码验证。

## 附件

- `port-lineage-diagram-v1.0.0.zip`：完整 Skill。
- `order-checkout-example.html`：离线交互示例。
- `order-checkout-diagram.svg`：可编辑矢量图。
- `order-checkout-preview.png`：原版本实际浏览器预览。
- `file-import-example.html`：第二个通用示例。
- `SHA256SUMS`：以上附件的 SHA-256 校验值。
