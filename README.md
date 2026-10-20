# Port Lineage Diagram

一个用于绘制**流程与字段血缘一体图**的 Agent Skill。
处理步骤是节点，字段是端口，连线解释数据从哪里来、经过哪些变化、流向哪里。
支持非线性分支、汇合、跨步骤透传和外部配置来源；输出离线交互 HTML 与可编辑 SVG。

## 先看效果

![订单结算：流程与字段血缘一体图](docs/demos/order-checkout/qa/overview.png)

订单示例把价格计算与运费查表分为两条独立依赖分支，再汇合结算。
点击订单号、运费、应付金额，分别查看透传、查表和多来源计算。另有文件导入示例，展示不同业务模型的复用。

[订单结算示例](docs/demos/order-checkout/index.html) · [文件导入示例](docs/demos/file-import/index.html)

GitHub 文件页不执行 HTML 交互；下载 HTML 后用支持 JavaScript 的浏览器打开。HTML 自包含，不依赖 CDN 或后端服务。

## 安装

使用 [Skills CLI](https://github.com/vercel-labs/skills) 安装，在当前项目执行：

```bash
npx skills add PengZirong/port-lineage-diagram --skill port-lineage-diagram
```

全局使用则加 `-g`：

```bash
npx skills add PengZirong/port-lineage-diagram --skill port-lineage-diagram -g
```

CLI 会让你选择目标 Agent；当前官方文档要求 Node.js 22.20+。Node.js 仅用于这个安装入口，绘图本身只需要 Python 3.10+。

也可手动复制 **`skills/port-lineage-diagram/`** 到所用 Agent 支持的 skills 目录，保留内部目录结构。
不要把整个仓库当作安装单元。具体发现路径与调用语法由客户端决定。

## 使用

将任务交给已加载 Skill 的 Agent：

> 使用 port-lineage-diagram，读取这个项目的导入模块，把处理流程和每个输出字段的来源画在同一张图中。保留分支、汇合、透传和配置来源，显示中文含义；只画必要字段，找不到来源不要猜。把模型和图写到当前项目的 output/import-lineage/，不要写入 Skill 安装目录。

只看示例时：

> 用端口式数据流图画一笔订单：价格与运费分别计算，最后汇合。订单号直接透传；解释每个输出字段的来源。提供交互 HTML、SVG，有浏览器时附 PNG。

Skill 负责读取材料、建立依赖模型、调用构建器、检查并交付。运行细节见 [SKILL.md](skills/port-lineage-diagram/SKILL.md)。

## 不通过 Agent，直接运行

以下命令在仓库根目录执行；只需要 Python 标准库：

```bash
python skills/port-lineage-diagram/scripts/lineage.py build \
  skills/port-lineage-diagram/assets/examples/order-checkout.json \
  --out output/checkout --strict
```

输出为 `index.html`、`diagram.svg`、`model.json`、`validation.json`。
自己的流程按 [模型契约](skills/port-lineage-diagram/references/model-contract.md) 写成 JSON，再用相同命令构建。

已有 Playwright 和本地 Chromium 时可额外截图：

```bash
python skills/port-lineage-diagram/scripts/browser_qa.py \
  output/checkout/index.html --out output/checkout/qa
```

脚本不联网下载依赖。浏览器不可用时，仍可使用 HTML/SVG，不会生成假的截图。

## 仓库结构

```text
skills/port-lineage-diagram/   实际安装单元：指令、脚本、模板、参考资料与输入示例
  SKILL.md
  scripts/
  references/
  assets/
docs/demos/                   可阅读的 HTML、SVG 和截图
docs/history/                 首版历史报告，不代表当前验证结果
tests/                        渲染器与打包回归测试
evals/                        Agent 触发与任务质量评估
tools/                        仅维护者使用的打包和发布工具
```

只在内层保留一个 `SKILL.md`，避免根目录 Skill 遮蔽它。安装格式遵循 [Agent Skills 规范](https://agentskills.io/specification)，不是客户端专用插件清单。

## 范围与限制

来源已定义不等于真实代码已验证。模型中的规则是说明文本，不会被执行；本项目不是业务引擎或任意语言的自动血缘分析器。
未版本化数据环不受支持；复杂布局需检查实际截图。示例是构造案例，不代表生产订单或文件导入系统。

## 开发与版本

[开发、测试与发布](docs/development.md) · [Skill 评估](evals/README.md) · [变更记录](CHANGELOG.md)

目录重构记录在 `Unreleased`，不移动或覆盖已有 `v1.0.0` 标签和 Release。当前不新增许可证授权；许可证选择与公开可见性分别处理。
