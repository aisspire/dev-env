# Shell config

记录 Shell、环境变量和 PATH 规则。

- WSL 与 Windows PATH 边界由 `/etc/wsl.conf` 控制。
- PATH 修改必须说明 owner 和影响范围。
- Secrets 不写入 `.bashrc` 或普通 Shell 配置。
- 复杂逻辑放入脚本，不在启动文件中散落。

## Bash 与 Codex 多配置入口

`mise.toml` 只让 mise 在 `~/.bashrc` 中维护自己的激活 marker 块，不备份或接管
整份 `.bashrc`。仓库把 [`bash_aliases`](bash_aliases) 以符号链接方式管理为
`~/.bash_aliases`；Ubuntu 默认的 `.bashrc` 会在交互式 Bash 启动时加载它。

该文件中的配置副本管理只提供增加和删除两个操作。增加操作把当前 `~/.codex` 完整复制到
`~/.codex-env/.codex-<name>`，并在文件末尾的受控块中生成
`codex-<name>` alias：

```bash
codex-env-add work
codex-work
```

如果 provider 已在 `~/.codex/config.toml` 中声明，可以只为本次启动指定 provider；
其余参数会原样传给 Codex：

```bash
codex-p example
codex-p example --model gpt-5.6-terra
```

生成的 alias 通过 `CODEX_HOME` 使用副本，但仍调用同一个 `codex` 程序。用户可以
自行修改副本中的配置。删除操作同时移除目录和受控块中的 alias：

```bash
codex-env-delete work
```

名称只允许字母、数字、下划线和连字符。`~/.codex-env` 视为可随时删除的临时目录，
不参与工作站数据留存。

修改声明后先运行：

```bash
./scripts/dev-env plan --scope mise
```

只有明确确认后才运行 `apply --scope mise`。如果目标机器已有自己的
`~/.bash_aliases`，普通 apply 不会强制覆盖，应先合并内容再决定是否接管。
