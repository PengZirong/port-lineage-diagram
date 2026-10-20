# 发布到 GitHub

固定目标：`PengZirong/port-lineage-diagram`，**公开仓库**，正式版本 `v1.0.0`。
本文件描述发布步骤，不代表仓库或 Release 已经存在。

## 运行

需要 Python 3.10+、Git 和已安装的 GitHub CLI。先在本机完成授权：

```bash
gh auth login --hostname github.com
```

在当前目录执行：

```bash
bash publish.sh
```

脚本会检查账号、运行单元测试、严格构建两个示例、打包附件、初始化本地仓库、
创建公开 GitHub 仓库、推送 `main` 和 `v1.0.0`，然后创建带附件的正式 Release。
完成后回读远端仓库、标签和 Release，并验证附件名称及 SHA-256。
不会自动创建 Pages 站点，也不会添加许可证。

仅本地检查和打包，不访问 GitHub：

```bash
bash publish.sh --check
```

## 中途失败

首次创建远端成功后，本地 `.publish-state.json` 记录仓库和提交信息（不含凭证）。
保留当前目录，然后执行：

```bash
bash publish.sh --resume
```

恢复只适用于本脚本已经创建的仓库，且本地提交没有变化。不会接管其他已有同名仓库。
已经存在的完整正式 Release 只会读取核验，不会覆盖。遇到同标签草稿或不匹配附件时会停止，要求人工检查；不会删除草稿、覆盖附件或强推标签。

## 本地修改

首次发布前可以修改内容。启动发布后请勿修改已经提交的文件或标签；需要变更时应创建新的版本。

## 官方命令文档

- https://cli.github.com/manual/gh_repo_create
- https://cli.github.com/manual/gh_release_create
- https://cli.github.com/manual/gh_release_view
