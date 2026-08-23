# WSL2 开发环境管理规范 v2

## 1. 定位

v2 继承 v1 的分层和 owner 原则，但把“由人记住需要同步哪些文件”改为“由程序读取一个期望状态、自动探查实际状态并安全收敛”。

核心目标：

- 日常操作尽可能少。
- 期望状态和实际状态都可被机器稳定读取。
- 安装 Java、Python、Node 或 apt 包时，不再手工同步多份清单。
- 默认只补齐缺失项和修复受管配置，不自动升级或删除。
- 未来增加 Docker、Windows bridge 等能力时，只增加配置和 adapter，不重写控制器。

v2 当前支持 Ubuntu 24.04+ 的 WSL2，覆盖 apt、mise 与 rustup。

## 2. v1 的繁琐点与 v2 的答案

v1 同时存在 apt 文本清单、runtime Markdown 表、mise 实际安装状态和纯文本 inventory。以安装一个 JDK 为例，容易出现以下人工步骤：

1. 执行安装命令。
2. 修改 runtime 文档。
3. 修改全局 mise 配置。
4. 重新生成 inventory。
5. 人工检查默认版本和 PATH 是否生效。

v2 将其收敛为：

1. 执行 `./scripts/dev-env add <spec>`。
2. 查看自动生成的计划并确认一次。

mise 在安装时自动维护 `mise.lock`，控制器在完成后自动刷新 `inventory/current.json`。不再手工维护第二份 runtime 版本表。

仍可直接编辑根目录 `mise.toml`，再运行 `plan/apply`；`add` 只是将这一标准流程
收敛为单命令入口，不引入新的期望状态来源。

Maven 的默认答案不同：项目应使用 Maven Wrapper（`mvnw`），因此通常不安装或同步工作站级 Maven。只有确实需要全局 Maven 时，才将它加入 `mise.toml` 的 `[tools]`，之后仍使用同一套 plan/apply 流程。

## 3. 核心原则

### 3.1 一个对象只有一个 owner 和一个期望状态入口

| 对象 | Owner | 期望状态入口 |
|---|---|---|
| Ubuntu 系统包 | apt | `mise.toml` 的 `[bootstrap.packages]` |
| Python / Node / Java | mise | `mise.toml` 的 `[tools]` |
| runtime 精确解析结果 | mise lock | `mise.lock` |
| Shell 中的 mise 激活 | mise bootstrap | `[bootstrap.mise_shell_activate]` |
| 工作站级 mise 配置链接 | mise dotfiles | `[dotfiles]` |
| Python 项目依赖 | uv | 项目的 `pyproject.toml` / `uv.lock` |
| Java 构建工具版本 | Maven/Gradle Wrapper | 项目仓库 |
| Rust toolchain/component/target | rustup | `rustup.toml` |
| 项目服务 | Docker Compose | 项目或环境仓库中的 Compose 文件 |

`mise bootstrap` 是 apt 的声明式调用层，不改变“系统包由 apt 拥有”这一边界。

### 3.2 探查代替人工同步

控制器每次从真实系统读取：

- `mise bootstrap status --json`
- `mise bootstrap plan --json`
- `mise ls --installed --json`
- `rustup --version`、`rustup toolchain list` 和 `rustup show`
- 各 toolchain 的本地 `rustc --version --verbose`、已安装 component/target
- `/etc/os-release`、`/proc/version` 和 init 信息

控制器不依赖人工填写“已安装”状态。本地 `inventory/current.json` 只是可重复生成的
observed snapshot，不是新的期望状态来源；公开模板忽略真实快照，只提交虚构的
`inventory/example.json` 说明结构。

### 3.3 默认安全收敛

默认 `apply`：

- 安装缺失的 apt 包。
- 安装缺失的 mise runtime。
- 安装缺失的 Rust toolchain，或补齐声明的 component/target。
- 修复 rustup profile 和默认 toolchain。
- 修复由本仓库声明的 dotfile 链接和 shell 激活块。
- 自动刷新结构化 inventory。

默认 `apply` 不会：

- 升级已安装 apt 包、mise runtime 或 Rust toolchain。
- 删除 inventory 中的 `extra` 工具、toolchain、component 或 target。
- 执行 `apt autoremove`。
- 覆盖未声明为受管资源的用户配置。
- 保存或输出 Secret 值。

删除、升级和迁移发行版必须是后续显式命令或独立计划，不能隐藏在普通收敛中。

### 3.4 稳定、结构化、可比较

所有 JSON 输出包含 `schema_version`，字段稳定排序。生成的 inventory 不包含：

- 生成时间戳。
- 用户名和 HOME。
- runtime 安装绝对路径。
- PATH、磁盘容量和其他高噪声字段。

因此同一环境连续生成两次 inventory，在状态不变时字节内容应相同。

## 4. 架构

```text
mise.toml ──────┐
mise.lock ──────┤  Desired State
rustup.toml ────┤
                ↓
         scripts/dev-env
               │
        AdapterRegistry
          ├── apt adapter
          ├── mise adapter
          ├── rustup adapter
          └── future adapters (docker/...)
               │
       probe → plan → confirm → apply
               │
               ├── stdout JSON / human summary
               └── inventory/current.json
```

控制器使用 Ubuntu 自带的 Python 3.11+ 和标准库，不引入虚拟环境或第三方依赖。
实际 apt、runtime、dotfile 和 shell 操作由 mise 的原生 bootstrap 引擎执行；
rustup adapter 使用 rustup 的本地 CLI，并只在确认后的缺失-manager 路径下载经
SHA256 验证的官方安装器。Python 层负责统一入口、归一化、确认、安全策略和稳定输出。

## 5. Source of Truth

### 5.1 `mise.toml`

`mise.toml` 是 apt 与 mise 的唯一机器可读期望状态，包含：

- mise 最低版本。
- 最小 apt 包集合。
- Python、Node、Temurin Java 的版本意图和默认顺序。
- Bash 激活声明。
- 全局 mise config/lock 到本仓库的 symlink 声明。
- 标准 `CARGO_HOME`、`RUSTUP_HOME` 和 `~/.cargo/bin` PATH。

版本意图使用系列版本，例如 Python `3.12` 和 Node `22`。数组第一项是工作站默认版本，项目目录中的 mise 配置仍可覆盖它。

### 5.2 `mise.lock`

`mise.lock` 保存 `linux-x64` 的精确版本、URL 和 checksum。`[settings] lockfile = true` 使 mise 在安装或升级时自动维护它。

日常安装缺失项不会主动 bump 已锁定版本。需要升级某个系列时应显式运行：

```bash
mise lock --platform linux-x64 --bump <tool>
./scripts/dev-env plan
./scripts/dev-env apply
```

### 5.3 `rustup.toml`

`rustup.toml` 是工作站 Rust 的唯一期望状态，声明 schema、默认 toolchain、安装
profile，以及每个 toolchain 的附加 components 和交叉 targets。当前默认 stable，
同时保留 nightly；两者使用 minimal profile 并增加 clippy、rust-analyzer、rustfmt。

channel 名保存意图，不另建自定义 lockfile。普通 apply 不更新已存在的 channel；
inventory 保存解析后的精确 Rust release 与 commit date。需要可复现编译器的项目
使用自己的 `rust-toolchain.toml`，并由 rustup 的标准优先级覆盖工作站默认值。

### 5.4 `inventory/current.json`

`inventory/current.json` 是本地生成文件，在公开模板中默认被 Git 忽略；
`inventory/example.json` 仅用于展示 schema。私人环境仓库可显式选择跟踪真实快照，
但它始终只是 observed state，不参与期望状态计算。

inventory 的顶层结构为：

```json
{
  "schema_version": 1,
  "platform": {},
  "adapters": {
    "apt": {},
    "mise": {},
    "rustup": {}
  },
  "summary": {
    "converged": true,
    "missing": 0,
    "extra": 0,
    "findings": 0
  }
}
```

每个 adapter 可报告：

- `desired`：声明的目标。
- `observed`：实际存在的受管对象。
- `missing`：需要补齐的对象。
- `extra`：存在但未声明的对象，仅观察、不自动删除。
- `findings`：shell、dotfile 等需要修复的配置漂移。

rustup adapter 另外输出 manager 版本、desired/observed 默认 toolchain 与 profile，
以及各受管 toolchain 的 release、commit date、host、components 和 targets。输出不含
HOME、rustup home、Cargo home 或安装绝对路径。

## 6. 统一命令

| 命令 | 是否修改状态 | 说明 |
|---|---:|---|
| `dev-env status [--json]` | 否 | 探查并显示当前状态 |
| `dev-env check [--json]` | 否 | 已收敛返回 0，有漂移返回 2，执行错误返回 1 |
| `dev-env plan [--json] [--scope ...]` | 否 | 有动作返回 2，无动作返回 0 |
| `dev-env apply [--scope ...]` | 是 | 先显示计划，只确认一次，然后收敛并刷新 inventory |
| `dev-env apply --yes` | 是 | 明确授权的非交互收敛 |
| `dev-env add [--yes] SPEC [SPEC...]` | 是 | 原子声明软件，显示计划并确认安装；`--yes` 跳过确认 |
| `dev-env inventory` | 否 | 原子更新 `inventory/current.json` |
| `bootstrap [--dry-run] [--yes]` | 可能 | 缺少 mise 时先安装，再调用统一 apply |

`--scope apt`、`--scope mise` 和 `--scope rustup` 可用于局部计划或收敛。无 scope
时按照 `apt → mise → rustup` 的 adapter 依赖顺序执行。

`scripts/inventory` 是兼容入口，只转发到 `dev-env inventory`。

### 6.1 添加软件

`add` 接受 mise 风格的 `<tool>@<version>` spec，未提供版本时默认为 `latest`：

```bash
./scripts/dev-env add apt:jq
./scripts/dev-env add node@26
./scripts/dev-env add aqua:openai/codex@latest
./scripts/dev-env add npm:@scope/agent@latest
./scripts/dev-env add --yes apt:jq aqua:openai/codex@latest
```

- `apt:` 前缀写入 `[bootstrap.packages]`，其余 spec 写入 `[tools]`。
- 一次调用的全部声明经过校验后原子写入，并自动推导 apt/mise scope。
- 已有数组追加版本，不改变第一项默认版本；已有标量版本不同则拒绝，避免把
  `add` 隐式变成升级命令。
- 配置暂存后复用 native plan。用户取消或 plan 失败时恢复原始字节和权限；
  apply 已开始后失败则保留声明并报告 drift，供修复后重试。
- `--yes` 仅跳过确认，不放宽版本冲突、TOML 校验或默认不删除策略。
- `add` 只处理 apt/mise；Rust 矩阵直接编辑 `rustup.toml`。

## 7. Bootstrap

`scripts/bootstrap` 是新机器上唯一需要记住的入口：

1. 读取 `/etc/os-release`，拒绝不受支持的平台。
2. 如果 mise 已存在，直接进入统一 plan/apply。
3. Ubuntu 26.04+ 使用官方 PPA 安装 mise。
4. Ubuntu 24.04–25.x 使用官方 extrepo 安装 mise。
5. mise 安装完成后继续同一次收敛；不会要求用户再手工同步配置。

`--dry-run` 不执行 sudo 或安装；`--yes` 只应在调用者已经审查配置和计划时使用。

## 8. Java 与 Maven 示例

当前工作站声明 Temurin 21 和 17，21 为默认版本。旧的未带 vendor 前缀的 JDK 会显示为 `extra`，但保留不动。

增加新的 JDK 系列：

```toml
[tools]
java = ["temurin-21", "temurin-17", "temurin-25"]
```

然后运行：

```bash
./scripts/dev-env plan --scope mise
./scripts/dev-env apply --scope mise
```

如果目标项目有 `mvnw` 或 `gradlew`，直接使用 Wrapper，不向工作站配置增加 Maven/Gradle。确需全局 Maven 时可在 `[tools]` 中增加 `maven = "<series>"`，adapter 会自动将它纳入探查、计划、安装和 inventory，无需增加一份 Markdown 清单。

## 9. Rust toolchain

rustup adapter 的只读路径不联网、不安装，也不把 `extra` 变成 remove 计划。缺失
manager 时，只有确认后的 apply 才执行以下安全路径：

1. 将当前架构映射为官方 `x86_64-unknown-linux-gnu` 或
   `aarch64-unknown-linux-gnu`；其他架构明确失败。
2. 若 PATH 中存在无法确认由 rustup 所有的 `rustc`/`cargo`，在下载前停止。
3. 从 `static.rust-lang.org/rustup/dist/<host>/` 下载 `rustup-init` 和 `.sha256`，
   在临时目录校验后直接执行，不使用远程 shell 管道或 sudo。
4. 安装器使用 `--no-modify-path --default-toolchain none --profile minimal`；PATH
   由 mise 的声明负责。

toolchain 收敛先安装默认 stable 并设为默认，再安装 nightly。新 toolchain 的安装
命令包含声明的 profile/components/targets 和 `--no-self-update`；浮动 nightly
增加 `--allow-downgrade`，避免选择缺少声明组件的最新快照。已有 toolchain 只调用
component/target add，不运行 update。因此已有 nightly 当前快照不提供某组件时会
保留 drift 并失败，不会隐式跳到另一个日期。

显式升级由用户直接运行 `rustup update <toolchain> --no-self-update`，然后刷新
inventory。交叉 target 通常还需要 linker/SDK，这些系统依赖不由 rustup adapter
推断或自动安装。实现依据为 rustup 官方的[安装](https://rust-lang.github.io/rustup/installation/)、
[profile](https://rust-lang.github.io/rustup/concepts/profiles.html)和
[交叉编译](https://rust-lang.github.io/rustup/cross-compilation.html)说明。

## 10. Adapter 扩展契约

`scripts/dev_env/adapters/` 下每个非私有模块可以导出一个 `ADAPTER`。控制器自动发现模块，并按 `depends_on` 拓扑排序。adapter 提供：

```python
name = "docker"
depends_on = ("apt",)

def probe(context): ...
def plan(context): ...
def apply(context, *, confirmed): ...
```

共享 `AdapterContext` 提供：

- `repo_root`：仓库根目录。
- `runner`：无 shell 拼接的统一命令执行器。
- `mise`：当前 mise 原生后端。
- `rustup`：当前 rustup 后端。
- 惰性缓存的 bootstrap status、plan 和 installed tools。

增加 adapter 不需要修改 `EnvironmentService` 或 CLI。adapter 输出统一的 `status/desired/observed/missing/extra/findings`，计划动作输出统一的 `adapter/kind/name/action/current/desired`。

### 10.1 未来 Docker 接入

优先顺序：

1. Compose 项目能由 mise `[bootstrap.compose]` 表达时，直接增加原生配置，由 mise 负责收敛。
2. Docker Engine/Desktop integration、daemon 健康、context、volume 备份等 mise 未覆盖状态，由 `docker.py` adapter 探查。
3. adapter 只管理明确声明的资源；volume 数据、数据库内容、镜像缓存不作为普通 desired state 删除或重建。

预计新增内容：

```text
scripts/dev_env/adapters/docker.py
scripts/dev_env/docker_backend.py        # 仅在逻辑较多时拆分
tests/test_docker_adapter.py
```

## 11. 旧版布局迁移

- `manifests/apt/bootstrap.txt` 合并到 `mise.toml` 后删除，避免双写。
- `manifests/runtimes/desired.md` 合并到 `mise.toml`/`mise.lock` 后删除。
- 旧的纯文本 `inventory/current` 替换为结构化 `inventory/current.json`。
- `scripts/inventory` 保留为兼容转发。
- `~/.config/mise/config.toml` 和 lock 由 dotfile symlink 指向仓库。
- mise 为 `.bashrc` 写入 marker 管理块后，控制器只删除块外完全相同的旧激活行，避免重复激活；其他 shell 内容不动。
- Java 切换为 Temurin 声明；已有 OpenJDK 只作为 extra 报告，不自动卸载。
- Rust stable/nightly、profile、components 和 targets 迁入 `rustup.toml`；精确
  release/commit date 只记录在可重新生成的 inventory。

## 12. 验收标准

v2 第一阶段满足以下条件：

- `mise.toml` 可被 Python `tomllib` 和 mise 同时解析。
- `mise.lock` 覆盖声明的全部 runtime 和 `linux-x64` 校验信息。
- `status/plan/check` 是只读的，JSON 可被其他程序直接解析。
- 连续生成两次无变化 inventory 时字节一致。
- `apply` 只执行计划中的 create/repair，不合成 remove 动作。
- apt、mise 和 rustup 可以独立 scope，也能按依赖顺序共同执行。
- Rust 缺失项只生成 create/repair；普通 apply 不更新或删除 toolchain。
- 缺少 rustup 时，SHA 不匹配、未知架构和外来 Rust 冲突都在执行安装器前失败。
- stable 在 nightly 前安装并设为默认；已有 toolchain 只补 component/target。
- adapter 自动发现、重复名、缺失依赖和循环依赖都有明确错误。
- 新增 adapter 无需改 CLI 和核心服务。

## 13. 一句话原则

> 人只维护机器可读的期望状态；程序负责探查、比较和安全收敛；锁文件记录精确版本；inventory 记录稳定事实；扩展通过 adapter 增长，而不是增加人工同步步骤。
