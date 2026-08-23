# Observed State

`current.json` 是由 `./scripts/dev-env inventory` 原子生成的本机实际状态，不手工修改，
并且在公开模板中默认被 Git 忽略。`example.json` 是完全虚构的结构示例，不代表任何
真实机器；私人环境仓库可以根据自己的备份边界显式跟踪 `current.json`。

- `schema_version` 允许消费者显式处理格式演进。
- 内容保持稳定排序，不含时间戳、HOME、安装路径、磁盘容量等机器噪声。
- `desired`、`observed`、`missing`、`extra` 和 `findings` 可直接供脚本或未来 WebUI 消费。
- `rustup` adapter 另记录 manager 版本、默认 toolchain、profile，以及各受管
  toolchain 的精确 Rust release/commit date、components 和 targets。
- `extra` 只用于观察，默认不触发删除，也不影响收敛判定。
- 生成 inventory 是只读探查，不安装、升级、卸载或自动下载工具。
