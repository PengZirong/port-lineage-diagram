---
name: port-lineage-diagram
description: 将代码、接口、Schema 或流程说明绘制为端口式数据流图（Port-based Dataflow），在同一张图中表达非线性流程、字段来源、透传、转换、分支和汇合。适用于“字段从哪里来”“流程与血缘画在一起”“第一种端口图”“字段流转图”“字段来源追踪”等需求。输出可离线打开的交互 HTML、可编辑 SVG、数据模型与来源校验；有浏览器时生成真实 PNG。默认中文说明、少量必要字段，不拆成独立流程图与血缘图。
compatibility: Python 3.10+ for the standard-library renderer. A modern browser for HTML. PNG and browser QA optionally require Playwright and an existing Chromium executable. No network, API keys, Node.js, or build service required for core rendering.
metadata:
  version: "1.0.0"
---

# 端口式流程与字段血缘一体图

把**节点当作处理步骤，把节点内的字段当作端口，把端口连线当作直接依赖**。
保持第一种图的卡片、端口、非线性分支、同图来源追踪表达，不退化成上下分离的两张图。

## 立即开始

先定位本 Skill 所在目录，以下命令均在该目录执行；不要把开发环境的绝对路径写进产物。

```bash
# 复现默认的常见案例：电商订单结算
python scripts/lineage.py build examples/order-checkout.json --out output/order-checkout --strict

# 任意项目：先构造遵守契约的 workflow.json
python scripts/lineage.py validate workflow.json
python scripts/lineage.py build workflow.json --out output/workflow --strict

# 查看某个字段的真实依赖闭包
python scripts/lineage.py trace workflow.json node_id.field_id
```

构建默认输出 `index.html`、`diagram.svg`、`model.json`、`validation.json`。
实际材料仍有未知来源时，先不加 `--strict` 生成带警示的草图；不得宣称来源完整。
优先复用随包脚本和查看器，不要每次重新搭建前端项目或手工写高亮名单。

## 默认设计约束

- **同图**：处理步骤、外部数据、配置、字段值依赖处在同一画布。侧栏只作解释，不承担主图缺失的血缘关系。
- **少字段**：从用户关心的最终输出反推直接依赖闭包。保留所有必要来源，省去范围外字段；不是把整张数据库表铺满画布。
- **中文 + 代码名**：每行显示中文含义、字段名、类型、操作及简短来源 / 规则。代码名过长可以缩略，但详情必须完整，重要含义不能被截断。
- **不凭空出现**：每个范围内字段必须有 `from`，或者显式 `origin`，或明确 `unknown`。同名不意味着透传。
- **非线性不改线性**：保留分支、汇合、跨步骤透传和外部来源；不要为了整齐而画不存在的顺序。
- **同名不混同**：字段身份用 `node_id.field_id`，不能只用 `field_id`。
- **交付可编辑结果**：主产物是程序生成的 HTML/SVG，而不是不可核对连线的概念效果图；PNG 来自实际浏览器渲染。

## 工作流程

### 1. 明确范围与事实等级

有代码 / 文档时先读真实材料。用户只要效果示例时采用日常案例，不默认套用医疗场景。
默认案例是**一笔单商品规格订单的结算**，不是生产商城的完整定价、税费或支付流程。

设置 `mode`：`example` 为构造案例，`design` 为设计提案，`grounded` 为基于材料的关系。
区分“来源已定义”与“代码已验证”。没有证据不得写 `status: verified`。
有遗漏时列出具体未知来源，不靠猜测补全到 100%。

### 2. 先建依赖模型，后画图

阅读 [模型契约](references/model-contract.md)。

从输出往前追踪：每个输出值来自哪些输入值？哪个键决定选择哪条记录？哪个条件决定是否存在？
将这些关系分别记录为 `value`、`selector`、`condition`。
输入、数据库、文件、API、配置、常量、运行时值都是合法根来源，但必须有明确 `locator`。

透传使用 `identity`；改名使用 `rename`；改类型使用 `cast`；计算必须写具体 `rule`。
查表不能只写“来自字典”：记录选择键与实际取值来源。
不要另外维护 `rootSources`、手写完整路径或字段名到高亮边的映射；由依赖图计算。

### 3. 明确非线性语义

独立的两条数据分支不自动代表已实现并行执行。只知道依赖时写“可独立计算”。
单请求上下文汇合不假装是数据库 JOIN；真正 JOIN 必须声明关联键、基数、冲突与未匹配策略。
有条件择支时用 `choose` 与逐依赖 `when`，声明互斥 / 穷尽条件及默认路径。
控制边放在 `controls`，不能用控制依赖冒充字段值来源。

循环数据用 `step_i0`、`step_i1` 等版本化节点展开；不能为消除环而删边。
当前渲染器允许控制回边，但拒绝未版本化的数据依赖环；它不是流程执行引擎。

### 4. 生成第一种图

参考 [绘图规则](references/drawing-rules.md)。

先用自动布局，再用 `position`、`width`、`routes` 微调；坐标要么全提供，要么全省略。
默认全部血缘可见；点击任一字段后聚焦真实上游闭包，其他路径弱化但节点保留。
“流程骨架”从同一份字段图折叠得到，不维护另一套可能不同步的流程图。

卡片使用紧凑输出映射：**左端是该输出的依赖接入口，右端是输出端口**。
多条入边不是多个值直接赋给同一个标量；它们由该行的转换 / 查表规则组合。
这是一种工程化 Port-based Dataflow 画法，不声称是严格 UML Pin 标准。

### 5. 校验、真实截图、查看后再交付

```bash
python -m unittest discover -s tests -v
python scripts/browser_qa.py output/workflow/index.html --out output/workflow/qa
# 如自动检测不到现有浏览器：追加 --browser /path/to/chromium
```

按 [验收清单](references/qa-checklist.md) 检查结果，至少逐个验证所有最终字段。
必须实际查看 PNG：文字不重叠，连线不穿过无关节点，箭头落到正确字段行。
自动检查只覆盖列出的项目，不把“测试通过”当成业务逻辑或代码语义已验证。
缺少浏览器时保留 HTML/SVG，明确没有完成截图验收，不伪造 PNG 或测试结论。

## 交付格式

交付 Skill 生成的 HTML、SVG、模型 JSON、校验报告；已完成截图时附 PNG。
对用户先展示图和文件入口，用极少文字指出范围、主要路径和未确认来源。
不要只输出 Mermaid、DOT 代码、文字解释或一张看不清字段的小缩略图。
不得自动把文件上传到仓库、覆盖源代码、发布站点或安装到用户目录，除非用户要求。

## 文件导航

- [模型契约](references/model-contract.md)：字段、来源、依赖角色与条件。
- [绘图规则](references/drawing-rules.md)：布局、样式、紧凑端口语义、常见误画。
- [验收清单](references/qa-checklist.md)：结构、视觉、交互与真实性。
- [调用评估样例](references/evaluation-prompts.md)：跨场景触发和反例。
- `examples/order-checkout.json`：7 个节点、5 个输出；透传、转型、查表、两分支汇合。
- `examples/file-import.json`：不同字段和节点，自动布局；文件解析 + 运行时来源。
- `assets/viewer.html`：离线 HTML + 原生 SVG/JS 模板，不依赖 CDN。
- `scripts/lineage.py`：验证、依赖追踪、布局与构建。
- `scripts/browser_qa.py`：可选 Chromium 验收与截图。

## 安全与边界

`rule`、`origin.locator`、`evidence` 都是描述性数据：不执行表达式，不打开任意路径，不读取凭证。
构建器不联网，不执行输入项目代码，不代替静态分析器或数据库血缘采集器。
脚本提供小中型图的布局基线，不保证任何大图一次自动布局就可读。复杂图必须真实渲染后调整。
若要求自动从代码精确提取血缘，先设计语言 / 框架特定的提取器，再用本 Skill 展示，不承诺已有该能力。
