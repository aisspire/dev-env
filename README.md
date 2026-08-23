# dev-env

可复用的 WSL2 声明式开发工作站模板：`mise.toml` 保存 apt、mise 和 shell
环境意图，`rustup.toml` 保存 Rust toolchain 矩阵，`mise.lock` 锁定 mise 工具的
精确版本，`dev-env` 负责探查、比较和安全收敛。

仓库自带一套偏完整的示例矩阵，覆盖多个 Python/Node 版本、Temurin Java、Rust、
uv 和 Codex。使用前先审查并按需要删改根目录的声明文件；普通 `apply` 不会删除
机器上已经存在的额外工具，也不会隐式升级已安装版本。

## 快速开始

```bash
./scripts/bootstrap                 # 新 WSL 或缺少 mise
./scripts/dev-env status            # 查看精简状态
./scripts/dev-env check --json      # CI 检查；漂移时返回 2
./scripts/dev-env plan              # 只预览，不修改环境
./scripts/dev-env plan --scope rustup
./scripts/dev-env apply             # 展示计划并确认一次
./scripts/dev-env add apt:jq node@26 # 声明并安装一个或多个工具
./scripts/dev-env inventory         # 更新本地实际状态快照
```

使用 `./scripts/dev-env --help` 或 `<命令> --help` 查看即时帮助。终端中绿色表示
成功/已收敛，黄色表示漂移/待执行，青色表示动作，红色表示错误；JSON、管道和
设置 `NO_COLOR` 时不使用颜色。

默认只补齐缺失项或修复受管配置，不自动升级、不删除额外工具、不执行
`apt autoremove`，也不保存 Secret。

工作站 Rust 默认声明 stable 与 nightly，并安装 clippy、rust-analyzer 和 rustfmt。
`dev-env add` 仍只修改 apt/mise 声明；调整 Rust 矩阵时直接编辑 `rustup.toml`，
再运行 `plan --scope rustup` 与 `apply --scope rustup`。

`inventory/current.json` 记录当前机器的 observed state，因此默认被 Git 忽略；
公开仓库只提供虚构的 [`inventory/example.json`](inventory/example.json) 说明结构。
私人环境仓库可按自己的备份策略显式跟踪实际快照。

完整参数、操作示例、退出码和故障恢复见 [完整操作手册](docs/operations.md)。

本项目采用 [MIT License](LICENSE)。
