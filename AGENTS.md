# AI 操作入口

本仓库是 WSL2 开发工作站的声明式 Source of Truth。优先使用
`./scripts/dev-env`，新环境或缺少 `mise` 时使用 `./scripts/bootstrap`。

## 工作规则

- 先读 `README.md`，再按需查阅 `docs/operations.md`。
- 只读检查使用 `status`、`check`、`plan`；修改环境前必须先展示计划。
- 只有用户明确授权时才运行 `apply`、`add`、`bootstrap --yes` 等写操作。
- 不自动升级、不删除 `extra` 工具、不执行 `apt autoremove`，不把 Secret 写入输出或 Git。
- `mise.toml` 是期望状态，`mise.lock` 是精确锁定，`inventory/current.json` 是可重新生成的实际状态。

## Git 分支与公开边界

- 未经用户明确要求不得创建 commit；用户只要求常规提交时，提交目标只能是
  `personal` 分支。
- `personal` 用于本机和个人环境的正常开发提交，可以包含经过 Secret 检查的
  机器相关声明与 alias，但仍不得提交 token、密码、私钥等 Secret。
- `main` 面向公开发布。只有用户在当前会话主动明确要求向 `main` 提交时，才可从
  `personal` 或工作区筛选可公开内容并创建 commit。
- 不直接将 `personal` merge 到 `main`。进入 `main` 的内容必须逐项审查，只提取
  通用代码、虚构示例、文档和测试；排除 `inventory/current.json`、个人 alias、
  账号或 provider 专用配置、私有端点以及机器特定路径。
- 在 `main` 提交前检查 staged diff，确认公开内容不依赖未公开的 personal 状态，
  且不包含 Secret 或可识别的个人环境信息。

## 验证

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

完整参数、操作示例、退出码和故障恢复见 [完整操作手册](docs/operations.md)。
