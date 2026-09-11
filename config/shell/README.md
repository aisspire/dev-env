# Shell config

记录 Shell、环境变量和 PATH 规则。

- WSL 与 Windows PATH 边界由 `/etc/wsl.conf` 控制。
- PATH 修改必须说明 owner 和影响范围。
- Secrets 不写入 `.bashrc` 或普通 Shell 配置。
- 复杂逻辑放入脚本，不在启动文件中散落。

## WSL 访问 Windows 代理

`bash_aliases` 提供 `proxy <port> [host [no_proxy]]` 与 `unproxy`。Windows 代理端口支持
HTTP/SOCKS5 混合协议时，通常只需指定一次端口：

```bash
proxy 10808
```

函数与 Windows 版本保持相同流程：同时设置大小写形式的 `http_proxy`、
`https_proxy`、`socks_proxy`、`socks5_proxy`、`all_proxy`、`no_proxy`，设置
`NODE_USE_ENV_PROXY=1`，最后通过 `curl` 请求 ipify 并显示当前出口 IP。
`all_proxy` 使用 HTTP URL，SOCKS 变量使用 SOCKS5 URL。运行 `unproxy` 可清除当前
Bash 会话中的这些变量。

主机地址默认是 `127.0.0.1`，也可以通过第二个参数指定：

```bash
proxy 10808 127.0.0.1
proxy 10808 172.20.0.1
```

第三个参数可以覆盖默认的 `localhost,127.0.0.1,::1`。在 WSL NAT 模式下使用
Windows 主机地址时，Windows 代理需要监听可从 WSL 访问的地址，并允许来自 WSL
虚拟网络的连接。

仓库已接管 `~/.bash_aliases` 时，修改后让当前终端立即生效：

```bash
source ~/.bash_aliases
```

新环境或尚未接管该文件时，先预览并经确认应用，再加载：

```bash
./scripts/dev-env plan --scope mise
./scripts/dev-env apply --scope mise
source ~/.bash_aliases
```

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
