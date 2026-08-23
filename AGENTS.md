# AI 操作入口

本仓库是 WSL2 开发工作站的声明式 Source of Truth。优先使用
`./scripts/dev-env`，新环境或缺少 `mise` 时使用 `./scripts/bootstrap`。

## 工作规则

- 先读 `README.md`，再按需查阅 `docs/operations.md`。
- 只读检查使用 `status`、`check`、`plan`；修改环境前必须先展示计划。
- 只有用户明确授权时才运行 `apply`、`add`、`bootstrap --yes` 等写操作。
- 不自动升级、不删除 `extra` 工具、不执行 `apt autoremove`，不把 Secret 写入输出或 Git。
- `mise.toml` 是期望状态，`mise.lock` 是精确锁定，`inventory/current.json` 是可重新生成的实际状态。

## 验证

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

完整参数、操作示例、退出码和故障恢复见 [完整操作手册](docs/operations.md)。
