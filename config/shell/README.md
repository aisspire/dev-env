# Shell config

记录 Shell、环境变量和 PATH 规则。

- WSL 与 Windows PATH 边界由 `/etc/wsl.conf` 控制。
- PATH 修改必须说明 owner 和影响范围。
- Secrets 不写入 `.bashrc` 或普通 Shell 配置。
- 复杂逻辑放入脚本，不在启动文件中散落。
