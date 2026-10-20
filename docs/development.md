# 开发、测试与发布

## 分清三种检查

日常 Agent 制图检查本次模型与浏览器输出。修改构建器、查看器或目录布局时运行仓库回归测试；修改 Skill 指令时另做 `evals/` 中的 Agent 任务评估。
程序测试通过不能代替 Agent 触发效果或真实项目的业务验证。

以下命令均在仓库根目录执行。任务和测试产物写入 `output/` 或 `dist/`，不污染安装目录。

```bash
python -m unittest discover -s tests -v
python skills/port-lineage-diagram/scripts/lineage.py build \
  skills/port-lineage-diagram/assets/examples/order-checkout.json \
  --out output/checkout --strict
python skills/port-lineage-diagram/scripts/lineage.py build \
  skills/port-lineage-diagram/assets/examples/file-import.json \
  --out output/import --strict
```

已有 Playwright 和 Chromium 时，分别运行 `browser_qa.py` 并实际查看截图。
`docs/demos/` 保留可阅读示例；改动渲染实现时应重新构建、验收后更新演示。旧结果位于 `docs/history/v1.0.0/`，不是当前测试结论。

## 安装验证

本地回归测试会将安装单元复制或链接到带空格的临时路径，从另外的项目目录构建，并检查安装树没有被写入。
这验证资源相对路径和独立运行，不等同于客户端自动发现或真实 Agent 调用。

在具备符合要求的 Node.js 和网络条件的环境，还应运行：

```bash
npx skills add . --list
npx skills add . --skill port-lineage-diagram
```

先在隔离的测试项目安装，再让目标 Agent 执行 `evals/prompts.md`。不要声称未运行的客户端测试已通过。
本地结构检查应只发现 `skills/port-lineage-diagram/SKILL.md`，根目录不留同名副本。

## 打包安装单元

```bash
python tools/package_skill.py --version v1.1.0-dev --out dist/preview
```

`--version` 是必填的制品版本标签；示例的 `v1.1.0-dev` 不表示已发布版本。
ZIP 只含 `port-lineage-diagram/SKILL.md`、随包脚本、参考资料、模板和小型输入模型，不含维护工具、完整截图、测试日志或历史发布资料。
同目录另生成 `SHA256SUMS`。打包器不会修改源码、创建 git 标签或联网；不同工作目录都可以调用它。

## 后续 Release

不再使用首版的一次性建库脚本，不限制仓库只能有一个提交。
维护者先确定版本和许可证决策，更新变更记录，测试并提交，再自行推送分支和不可变版本标签。
本工具只发布到已存在的仓库、已存在的远端标签；不创建仓库、不推送代码、不移动标签、不覆盖已有 Release。

1. 将本次说明写入项目内的 Markdown 文件，确认本地工作树干净。
2. 在 GitHub 已有目标版本标签后，先运行只检查/打包的默认模式：

```bash
python tools/publish_release.py --version v1.1.0 \
  --notes docs/releases/v1.1.0.md
```

上面的说明文件由维护者创建；仓库不预置尚未发布版本的虚假说明。该命令需要 GitHub CLI 已登录，会读取远端仓库和标签并构建本地安装包，但不会写入 GitHub。

3. 确认检查后，显式加 `--publish` 才会创建 Release 并上传 ZIP 与校验文件：

```bash
python tools/publish_release.py --version v1.1.0 \
  --notes docs/releases/v1.1.0.md --publish
```

发布前重新确认本地 HEAD、远端标签和本地标签指向同一提交；已有版本直接拒绝，不覆盖、不尝试恢复它。
工具故障时查看 GitHub 实际状态，尤其是可能部分创建的 Release；不要盲目重复执行写入。
历史 `v1.0.0` 标签和其附件保持不变。安装包下载和演示展示是分离的，完整示例继续放在 `docs/demos/`。

本轮目录迁移的实际结果见 [重构验收](verification/skill-layout.md)。
