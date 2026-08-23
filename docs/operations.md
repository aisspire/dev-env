# dev-env 完整操作手册

本文是仓库的用户操作参考，覆盖所有入口、参数、退出码、副作用、示例和失败
恢复方式。架构和扩展契约另见
[WSL2 开发环境管理规范 v2](wsl2-dev-environment-spec-v2.md)。

## 1. 基本约定

仓库提供两个正式入口：

```text
./scripts/bootstrap   新环境初始化；缺少 mise 时也能运行
./scripts/dev-env     日常探查、计划、收敛和添加软件
```

`dev-env` 的所有子命令都支持 `-h`/`--help`：

```bash
./scripts/dev-env --help
./scripts/dev-env status --help
./scripts/dev-env check --help
./scripts/dev-env plan --help
./scripts/dev-env apply --help
./scripts/dev-env add --help
./scripts/dev-env inventory --help
./scripts/bootstrap --help
```

即使尚未安装 `mise`，帮助命令仍然可用；执行其他 `dev-env` 命令时若缺少
`mise`，程序会提示先运行 `./scripts/bootstrap`。

### 1.1 状态来源

| 文件 | 含义 | 是否手工修改 |
|---|---|---:|
| `mise.toml` | apt、mise runtime、dotfile、shell 激活和 Rust HOME/PATH 的期望状态 | 是 |
| `mise.lock` | Linux x64 runtime 的精确版本、URL 和校验和 | 否，由 mise 维护 |
| `rustup.toml` | Rust toolchain、component、target、profile 和默认值的期望状态 | 是 |
| `inventory/current.json` | 本地生成的实际状态快照；公开模板默认忽略 | 否，由 `inventory` 更新 |
| `inventory/example.json` | 完全虚构的 inventory schema 示例 | 否，仅供参考 |

### 1.2 颜色

人类可读输出在交互终端中使用以下颜色：

| 颜色 | 含义 |
|---|---|
| 绿色 | 成功、已收敛或已写入快照 |
| 黄色 | 存在漂移或有待执行动作 |
| 青色 | `create`、`repair`、`add` 等具体动作 |
| 红色 | 错误或用户取消 |

重定向、管道和 `--json` 输出不会包含 ANSI 颜色。需要在交互终端中禁用颜色时：

```bash
NO_COLOR=1 ./scripts/dev-env status
```

### 1.3 安全边界

默认收敛只会创建缺失对象或修复受管配置：

- 不自动升级已经存在的工具；
- 不删除 inventory 中的 `extra` 工具、Rust toolchain、component 或 target；
- 不执行 `apt autoremove`；
- 不修改项目仓库自己的依赖；
- 不把 token、密码、私钥等 Secret 写入输出或 Git。

## 2. 命令总览

| 命令 | 修改系统 | 成功 | 特殊退出码 |
|---|---:|---:|---|
| `bootstrap` | 可能 | 0 | 取消、平台不支持或执行失败为 1 |
| `status` | 否 | 0 | 执行错误为 1 |
| `check` | 否 | 0 | 有漂移为 2，执行错误为 1 |
| `plan` | 否 | 0 | 有待执行动作为 2，执行错误为 1 |
| `apply` | 是 | 0 | 取消或执行失败为 1 |
| `add` | 是 | 0 | 取消、声明无效或执行失败为 1 |
| `inventory` | 只写本地快照 | 0 | 执行错误为 1 |

退出码 `2` 表示“命令成功发现差异”，不是程序崩溃。

## 3. `bootstrap`：初始化新环境

### 用法

```text
./scripts/bootstrap [--dry-run] [--yes] [--scope ADAPTER]
```

| 参数 | 作用 |
|---|---|
| `--dry-run` | 只显示安装命令；若 mise 已存在，则运行只读 `plan` |
| `--yes` | 跳过确认，仅用于已经审查配置和计划的自动化执行 |
| `--scope ADAPTER` | 只收敛指定 adapter；可重复，当前为 `apt`、`mise`、`rustup` |
| `-h`, `--help` | 显示帮助后退出 |

支持 Ubuntu 24.04 或更新版本。Ubuntu 26.04+ 通过官方 PPA 安装 mise，Ubuntu
24.04–25.x 通过官方 extrepo 安装。mise 安装完成后，脚本会在同一次运行中
转交给 `dev-env apply`。

### 示例：首次预览

```bash
./scripts/bootstrap --dry-run
```

可能输出：

```text
dry-run: sudo apt update
dry-run: sudo apt install -y software-properties-common
dry-run: sudo add-apt-repository -y ppa:jdxcode/mise
...
dry-run: /path/to/dev-env/scripts/dev-env apply
```

### 示例：交互式初始化

```bash
./scripts/bootstrap
```

缺少 mise 时会先询问是否安装；已经安装 mise 时会展示计划，并由 `apply`
询问一次是否执行。

### 示例：无人值守初始化

```bash
./scripts/bootstrap --yes
```

仅在调用者已经审查 `mise.toml`、`rustup.toml` 和预期计划时使用。

### 示例：只处理一个 adapter

```bash
./scripts/bootstrap --dry-run --scope mise
./scripts/bootstrap --yes --scope rustup
```

## 4. `status`：查看当前状态

### 用法

```text
./scripts/dev-env status [--json]
```

`status` 会实时探查 apt、mise runtime、dotfile、shell 激活和 rustup 状态，不修改
系统，也不写入 `inventory/current.json`。Rust 探查只运行本地只读命令，不检查
远端 channel，也不会自动安装 rustup 或 toolchain。

### 示例：人类可读摘要

```bash
./scripts/dev-env status
```

已收敛：

```text
state=converged missing=0 extra=0 findings=0
详细操作见: docs/operations.md
```

存在漂移：

```text
state=drift missing=2 extra=1 findings=1
详细操作见: docs/operations.md
```

字段含义：

- `missing`：声明了但尚未满足的包、工具或版本数量；
- `extra`：已安装但未声明的 mise 或 Rust 对象数量，仅观察、不自动删除；
- `findings`：dotfile、shell 激活、Rust profile/default 等受管配置问题数量。

`status` 即使发现漂移也返回 `0`；需要用退出码判断漂移时使用 `check`。

### 示例：机器可读状态

```bash
./scripts/dev-env status --json
```

输出结构：

```json
{
  "adapters": {
    "apt": {
      "desired": [],
      "extra": [],
      "findings": [],
      "missing": [],
      "observed": [],
      "status": "converged"
    },
    "mise": {
      "desired": [],
      "extra": [],
      "findings": [],
      "missing": [],
      "observed": [],
      "status": "converged"
    },
    "rustup": {
      "available": true,
      "default_toolchain": {
        "desired": "stable",
        "observed": "stable"
      },
      "desired": [],
      "extra": [],
      "findings": [],
      "manager": {
        "version": "1.29.0"
      },
      "missing": [],
      "observed": [],
      "profile": {
        "desired": "minimal",
        "observed": "minimal"
      },
      "status": "converged"
    }
  },
  "platform": {},
  "schema_version": 1,
  "summary": {
    "converged": true,
    "extra": 0,
    "findings": 0,
    "missing": 0
  }
}
```

实际数组会包含完整对象；Rust observed 项还包含精确 `release`、`commit_date`、
`components`、`targets` 和 host triple。输出不包含 HOME 或安装绝对路径。

## 5. `check`：用退出码检查漂移

### 用法

```text
./scripts/dev-env check [--json]
```

输出内容与 `status` 相同，但退出码适合 CI、定时任务和 shell 脚本：

| 退出码 | 含义 |
|---:|---|
| 0 | 已收敛 |
| 2 | 成功完成探查，但存在漂移 |
| 1 | 探查失败 |

### 示例：人工检查

```bash
./scripts/dev-env check
```

### 示例：CI 保存 JSON

```bash
if ./scripts/dev-env check --json > /tmp/dev-env-check.json; then
  echo "environment converged"
else
  result=$?
  if [ "$result" -eq 2 ]; then
    echo "environment drift detected"
  else
    echo "environment check failed" >&2
    exit "$result"
  fi
fi
```

## 6. `plan`：预览收敛动作

### 用法

```text
./scripts/dev-env plan [--json] [--scope ADAPTER]
```

| 参数 | 作用 |
|---|---|
| `--json` | 输出稳定的机器可读计划，不使用颜色 |
| `--scope ADAPTER` | 只计划指定 adapter，可重复 |

当前 scope：

- `apt`：Ubuntu apt 软件包；
- `mise`：runtime、工具、dotfile 和 shell 激活；
- `rustup`：Rust manager、toolchain、component、target、profile 和默认值。

不提供 scope 时检查全部 adapter。未知 scope 会返回 `1` 并列出错误。

### 示例：预览全部动作

```bash
./scripts/dev-env plan
```

存在动作时可能输出：

```text
create apt:package apt:jq
repair mise:dotfile ~/.config/mise/config.toml
create mise:tool node@26
create rustup:toolchain nightly
total=4
详细操作见: docs/operations.md
```

此时退出码为 `2`。无动作时输出：

```text
total=0
详细操作见: docs/operations.md
```

并返回 `0`。

### 示例：只预览一个 adapter

```bash
./scripts/dev-env plan --scope apt
./scripts/dev-env plan --scope mise
./scripts/dev-env plan --scope rustup
```

### 示例：读取 JSON 计划

```bash
./scripts/dev-env plan --json
```

```json
{
  "actions": [
    {
      "action": "create",
      "adapter": "mise",
      "current": "missing",
      "desired": "26.0.0",
      "kind": "tool",
      "name": "node@26"
    }
  ],
  "schema_version": 1,
  "summary": {
    "create": 1,
    "repair": 0,
    "total": 1
  }
}
```

在启用 `set -e` 的 shell 中，计划退出码 `2` 需要显式处理：

```bash
set +e
./scripts/dev-env plan --json > /tmp/dev-env-plan.json
result=$?
set -e
if [ "$result" -ne 0 ] && [ "$result" -ne 2 ]; then
  exit "$result"
fi
```

## 7. `apply`：执行收敛

### 用法

```text
./scripts/dev-env apply [--yes] [--scope ADAPTER]
```

| 参数 | 作用 |
|---|---|
| `--yes` | 跳过交互确认 |
| `--scope ADAPTER` | 只收敛指定 adapter，可重复 |

执行顺序：

1. 生成并展示计划；
2. 无动作时不询问，直接刷新 inventory；
3. 有动作时询问一次；
4. 确认后执行 `create`/`repair`；
5. 重新探查并原子更新 `inventory/current.json`。

全部 adapter 同时执行时依赖顺序为 `apt → mise → rustup`。Rust scope 内先确保
默认 stable 完整并设为默认，再处理 nightly；普通 apply 不更新已安装编译器，
也不处理任何 `extra`。

### 示例：交互式收敛

```bash
./scripts/dev-env apply
```

```text
create mise:tool node@26
total=1
Apply these changes? [y/N] y
result=applied
详细操作见: docs/operations.md
```

输入不是 `y` 或 `yes` 时取消并返回 `1`，计划中的系统变更不会执行。

### 示例：只收敛一个 scope

```bash
./scripts/dev-env apply --scope apt
./scripts/dev-env apply --scope mise
./scripts/dev-env apply --scope rustup
```

### 示例：已审查计划后的自动执行

```bash
./scripts/dev-env plan --scope mise
./scripts/dev-env apply --yes --scope mise
```

`--yes` 只跳过确认，不放宽配置校验，也不会启用升级或删除。

## 8. `add`：声明并安装软件

### 用法

```text
./scripts/dev-env add [--yes] SPEC [SPEC ...]
```

`add` 接受一个或多个 apt/mise spec：

| 形式 | 归属 | 示例 |
|---|---|---|
| `apt:PACKAGE` | apt | `apt:jq` |
| `TOOL@VERSION` | mise | `node@26` |
| `TOOL` | mise，版本默认为 `latest` | `usage` |
| `aqua:OWNER/TOOL@VERSION` | mise aqua backend | `aqua:openai/codex@latest` |
| `npm:PACKAGE@VERSION` | mise npm backend | `npm:typescript@latest` |
| `npm:@SCOPE/PACKAGE@VERSION` | mise npm backend | `npm:@scope/tool@latest` |

处理流程：

1. 校验一次调用中的所有 spec；
2. 原子暂存到 `mise.toml`；
3. 自动推导 `apt`/`mise` scope 并展示计划；
4. 询问一次是否保留声明并安装；
5. 安装后刷新 inventory。

`add` 不修改 `rustup.toml`，也不接受 Rust toolchain/component/target spec。Rust
矩阵的变更必须直接编辑声明文件，让版本和默认值变化在 Git diff 中可见。

### 示例：添加 apt 软件包

```bash
./scripts/dev-env add apt:jq
```

会在 `[bootstrap.packages]` 中声明：

```toml
"apt:jq" = "latest"
```

### 示例：添加 runtime

```bash
./scripts/dev-env add node@26
./scripts/dev-env add python@3.13
./scripts/dev-env add java@temurin-25
```

### 示例：添加 aqua 或 npm 工具

```bash
./scripts/dev-env add aqua:openai/codex@latest
./scripts/dev-env add npm:typescript@latest
./scripts/dev-env add npm:@scope/tool@latest
```

### 示例：一次添加多个对象

```bash
./scripts/dev-env add apt:jq node@26 aqua:owner/tool@latest
```

只有所有 spec 都通过校验，配置才会被暂存。

### 示例：自动化添加

```bash
./scripts/dev-env add --yes apt:jq node@26
```

仅在调用者已经审查声明含义时使用。

### 已有声明的规则

- 不存在的 key：新增字符串声明；
- 已有字符串且版本相同：保持不变；
- 已有字符串但版本不同：拒绝，避免把 `add` 变成升级命令；
- 已有版本数组：新版本追加到末尾，第一项仍是默认版本；
- 数组已有该版本：保持不变；
- 数组必须是单行 TOML，`add` 才能安全追加。

例如已有：

```toml
node = ["22", "20"]
```

执行：

```bash
./scripts/dev-env add node@26
```

确认后变为：

```toml
node = ["22", "20", "26"]
```

默认版本仍为第一项 `22`。

### 取消和失败恢复

- 用户取消：恢复 `mise.toml` 的原始字节和权限；
- native plan 失败：恢复原配置；
- 安装开始后失败或被中断：保留新声明，并尽力刷新 inventory；修复外部问题后
  运行 `plan` 和 `apply` 重试。

## 9. `inventory`：更新实际状态快照

### 用法

```text
./scripts/dev-env inventory
```

该命令实时探查环境，并原子写入 `inventory/current.json`。探查过程不会安装、
升级或卸载软件。公开模板默认忽略这个文件，避免发布机器实际状态；
`inventory/example.json` 只用于说明输出结构。

### 示例

```bash
./scripts/dev-env inventory
```

```text
inventory=/path/to/dev-env/inventory/current.json
详细操作见: docs/operations.md
```

兼容入口：

```bash
./scripts/inventory
```

它只转发到 `./scripts/dev-env inventory`。不要手工修改生成的 JSON。

## 10. 直接编辑期望状态

复杂 apt/mise 变更可直接编辑根目录 `mise.toml`，然后使用统一流程：

```bash
./scripts/dev-env plan
./scripts/dev-env apply
git diff -- mise.toml mise.lock
```

### 添加 apt 包

```toml
[bootstrap.packages]
"apt:ripgrep" = "latest"
```

### 设置多个 runtime 版本

数组第一项是默认版本：

```toml
[tools]
python = ["3.13", "3.12", "3.11"]
node = ["24", "22", "20"]
java = ["temurin-25", "temurin-21", "temurin-17"]
```

### 添加工作站级工具

```toml
[tools]
"aqua:openai/codex" = "latest"
"npm:typescript" = "latest"
```

项目依赖应继续放在项目自己的配置和 lockfile 中。若项目提供 `mvnw`、
`gradlew` 等 Wrapper，优先使用 Wrapper，不在工作站级重复声明。

## 11. Rust toolchain

### 工作站声明

根目录 `rustup.toml` 是 Rust 的唯一工作站级期望状态：

```toml
schema_version = 1
default_toolchain = "stable"
profile = "minimal"

[toolchains.stable]
components = ["clippy", "rust-analyzer", "rustfmt"]
targets = []

[toolchains.nightly]
components = ["clippy", "rust-analyzer", "rustfmt"]
targets = []
```

`targets = []` 表示不声明交叉 target；rustup 自动包含 WSL 原生 host target。
未来可以增加官方版本（如 `1.92.0`）、日期 channel（如
`nightly-2026-08-20`）和交叉 target。schema 会拒绝未知字段、未声明的默认
toolchain、非法 profile、重复项和可能被解释为命令参数的不安全名称。

变更后先只读预览，再确认收敛：

```bash
./scripts/dev-env plan --scope rustup
./scripts/dev-env apply --scope rustup
```

重新打开 Bash 后，`mise.toml` 声明的 `CARGO_HOME`、`RUSTUP_HOME` 和
`~/.cargo/bin` PATH 才会完整进入新 shell。rustup 安装器始终使用
`--no-modify-path`，不会自行编辑 `.bashrc`。

### 安装与收敛边界

- `status`、`check`、`plan` 和 `inventory` 只运行本地只读 rustup/rustc 命令，
  不访问 channel 服务器；
- 缺少 rustup 时，确认后的 apply 才从 Rust 官方静态站点下载当前 WSL 原生
  `x86_64` 或 `aarch64` 的 `rustup-init` 与 SHA256，在临时目录验证后直接执行；
- 不使用远程 shell 管道或 sudo，安装参数固定包含 `--no-modify-path`、
  `--default-toolchain none` 和 `--profile <声明值>`（当前为 `minimal`）；
- 若 PATH 中已有无法确认由 rustup 所有的 `rustc` 或 `cargo`，安装会在下载前
  停止，不覆盖也不删除它们；
- 新建 toolchain 带上声明的 profile/components/targets 和 `--no-self-update`；
  新建浮动 `nightly` 另使用 `--allow-downgrade`，以选择包含全部声明组件的最新
  可用快照；
- 已有 toolchain 只补缺失 component/target，不运行 update；已有但未声明的
  toolchain/component/target 只进入 `extra`，不影响收敛，也不自动删除。

这些约束对应 rustup 的[安装说明](https://rust-lang.github.io/rustup/installation/)、
[组件与 profile](https://rust-lang.github.io/rustup/concepts/profiles.html)以及
mise 的[环境与 PATH 声明](https://mise.jdx.dev/environments/)。

### 显式升级

`stable`/`nightly` 保存 channel 意图，不使用自定义 Rust lockfile。普通 apply
不会拉取新快照；精确 Rust release 与 commit date 由 inventory 和 Git 历史记录。
确实要升级时，显式执行对应 owner 的更新命令，再刷新快照：

```bash
rustup update stable --no-self-update
rustup update nightly --no-self-update
./scripts/dev-env inventory
git diff -- rustup.toml
```

只升级需要的 channel。升级是独立的显式操作，不应隐藏在日常 apply 中。

### nightly 组件失败与恢复

已有 nightly 缺少组件时，adapter 只对当前已安装快照执行 `component add`。如果
该快照不提供组件，命令会安全失败，声明和 drift 都保留；adapter 不隐式更新
nightly，也不改成另一个日期。可等待上游恢复后重试、显式升级 nightly，或在
审查可用快照后把声明改为具体 `nightly-YYYY-MM-DD`，再重新 plan/apply。

SHA 不匹配、架构不受支持或发现外来 Rust 命令时，安装器不会执行。先用
`command -v rustup rustc cargo` 确认 owner 并人工解决冲突；本工具不会替用户
卸载或覆盖现有 Rust。

### 项目级边界

需要精确 Rust 版本的项目应在自己的仓库提交 `rust-toolchain.toml`，并可在其中
声明项目所需 components/targets。项目文件按 rustup 的正常优先级覆盖工作站
默认 toolchain；不要把项目 pin 复制到工作站 `rustup.toml`。Cargo 依赖仍由项目
的 `Cargo.toml`/`Cargo.lock` 管理，本仓库不安装全局 Cargo CLI。

## 12. 常用操作组合

### 日常只读检查

```bash
./scripts/dev-env status
./scripts/dev-env plan
```

### 修复发现的漂移

```bash
./scripts/dev-env check
./scripts/dev-env plan
./scripts/dev-env apply
```

### 只修复 shell、dotfile 和 runtime

```bash
./scripts/dev-env plan --scope mise
./scripts/dev-env apply --scope mise
```

### 只检查并补齐 Rust

```bash
./scripts/dev-env plan --scope rustup
./scripts/dev-env apply --scope rustup
```

### 更新并检查本地快照

```bash
./scripts/dev-env inventory
python3 -m json.tool inventory/current.json >/dev/null
```

### 无颜色日志

```bash
NO_COLOR=1 ./scripts/dev-env plan > /tmp/dev-env-plan.txt
```

### 维护者运行测试

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

## 13. 常见问题

### `mise is not installed`

先预览，再初始化：

```bash
./scripts/bootstrap --dry-run
./scripts/bootstrap
```

### `plan` 返回 2

这是“存在待执行动作”，不是执行错误。阅读计划后决定是否运行 `apply`。

### `unknown adapter`

检查 `--scope` 拼写。当前用户可用 scope 为：

```text
apt
mise
rustup
```

### `add will not replace it`

已有标量声明与请求版本不同。若确实要改变版本，请直接编辑 `mise.toml`，然后
运行 `plan` 和 `apply`；这会让升级意图在 Git diff 中清晰可见。

### inventory 中出现 `extra`

`extra` 表示存在未声明的 mise 工具或 Rust toolchain/component/target，不影响默认
收敛判断，也不会自动删除。确认不再需要后，应使用对应 owner 的精确卸载命令
人工处理，再刷新 inventory。

### apply 失败

不要删除声明或 lockfile。先阅读错误并修复网络、sudo、上游仓库或构建依赖，
然后重新运行：

```bash
./scripts/dev-env plan
./scripts/dev-env apply
./scripts/dev-env check
```

### 输出中为什么没有颜色

颜色只用于交互 TTY。JSON、重定向、管道以及存在 `NO_COLOR` 环境变量时均为
纯文本，便于脚本稳定解析。
