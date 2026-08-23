# mise config

工作站级 mise 配置已统一到仓库根目录的 `mise.toml` 和 `mise.lock`。

- `mise.toml` 保存版本意图和默认版本顺序。
- `mise.lock` 保存精确版本、URL 和 checksum，并由 mise 在安装/升级时维护。
- `mise bootstrap dotfiles` 将两者链接为 `~/.config/mise/config.toml` 和 `~/.config/mise/mise.lock`。
- `[env]` 声明标准 `CARGO_HOME`、`RUSTUP_HOME` 和 `~/.cargo/bin` PATH；rustup
  安装器不修改 shell 启动文件。
- 项目级配置仍由项目仓库负责，并覆盖工作站默认值。
- 不与 `pyenv`、`nvm`、`sdkman` 等重叠管理器并用。
- Rust toolchain 不交给 mise 管理；其独立期望状态位于根目录 `rustup.toml`。
