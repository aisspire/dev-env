# Docker config

记录 Docker Desktop / WSL integration 和 Compose 相关约定。

- 后续接入时优先使用 `mise.toml` 的 `[bootstrap.compose]` 表达可声明的 Compose 项目。
- mise 未覆盖的 Engine/Desktop integration、daemon health、context 和备份状态通过 `scripts/dev_env/adapters/docker.py` 扩展。
- Compose 文件描述服务，不把 volume 数据当作配置。
- 镜像缓存、volume 和数据库数据需要独立备份策略。
- 不在此目录保存真实 `.env` 或 Secret 值。
