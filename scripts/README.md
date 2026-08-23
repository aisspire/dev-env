# scripts

- `dev-env`：统一入口，提供 `status`、`check`、`plan`、`apply`、`add` 和 `inventory`。
- `bootstrap`：检查 Ubuntu/mise，必要时安装 mise，再交给 `dev-env apply` 收敛；支持 `--dry-run`、`--yes` 和 `--scope`。
- `inventory`：v1 兼容入口，转发到 `dev-env inventory`。
- `dev_env/`：仅使用 Python 标准库的控制器、归一化逻辑和 apt/mise/rustup adapter。

只读命令不会安装、升级、删除或下载工具。状态变更统一经过计划和一次确认；脚本不得把 Secret 写入输出、日志或 Git。

`dev-env add [--yes] SPEC [SPEC...]` 原子修改根目录 `mise.toml`，然后复用统一
plan/apply 流程。用户在确认前取消或 native plan 失败时恢复原配置；安装已经
开始后发生失败则保留期望状态，便于修复环境后重试。

Rust 声明不经过 `add`。直接编辑 `rustup.toml` 后使用 `--scope rustup`；只读
探查不会联网，缺少 rustup 时仅在确认后的 apply 下载并校验官方安装器。

完整参数和示例见 [`docs/operations.md`](../docs/operations.md)。
