# config

保存工作站配置模板和适配说明。

- apt、mise runtime、shell activation 和 Rust 环境变量位于根目录 `mise.toml`。
- Rust toolchain、component 和交叉 target 意图位于根目录 `rustup.toml`。
- 配置可以进入 Git，但不得包含 Secret 实际值。
- 配置变更应说明影响范围和恢复方式。
- 项目配置不放入这里，由项目仓库自行管理。
