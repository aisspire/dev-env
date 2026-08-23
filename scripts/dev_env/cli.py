from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Callable, Sequence, TextIO


REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPO_ROOT / "inventory" / "current.json"
MANUAL_PATH = "docs/operations.md"


class TerminalStyle:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _paint(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def green(self, text: str) -> str:
        return self._paint(text, "32")

    def yellow(self, text: str) -> str:
        return self._paint(text, "33")

    def cyan(self, text: str) -> str:
        return self._paint(text, "36")

    def red(self, text: str) -> str:
        return self._paint(text, "31")

    def bold_green(self, text: str) -> str:
        return self._paint(text, "1;32")

    def bold_yellow(self, text: str) -> str:
        return self._paint(text, "1;33")


def terminal_style(stream: TextIO) -> TerminalStyle:
    is_tty = getattr(stream, "isatty", lambda: False)()
    return TerminalStyle(bool(is_tty) and "NO_COLOR" not in os.environ)


def write_manual_hint(stream: TextIO) -> None:
    stream.write(f"详细操作见: {MANUAL_PATH}\n")


def write_error(message: str, stream: TextIO) -> None:
    stream.write(f"{terminal_style(stream).red(message)}\n")
    write_manual_hint(stream)


def _command_parser(subparsers, name: str, *, help_text: str, description: str, examples: str):
    return subparsers.add_parser(
        name,
        help=help_text,
        description=description,
        epilog=f"示例:\n{examples}\n\n完整操作手册: {MANUAL_PATH}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dev-env",
        description="查看、比较并收敛 WSL2 开发环境。",
        epilog=f"完整操作手册: {MANUAL_PATH}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    status = _command_parser(
        subparsers,
        "status",
        help_text="查看当前环境摘要",
        description="探查实际环境并显示收敛状态；不会修改系统。",
        examples="  dev-env status\n  dev-env status --json",
    )
    status.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="输出稳定的机器可读 JSON；不使用颜色",
    )

    check = _command_parser(
        subparsers,
        "check",
        help_text="检查是否存在配置漂移",
        description="探查环境并用退出码表示是否收敛；适合 CI 和脚本。",
        examples="  dev-env check\n  dev-env check --json",
    )
    check.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="输出稳定的机器可读 JSON；不使用颜色",
    )

    plan = _command_parser(
        subparsers,
        "plan",
        help_text="预览为达到期望状态所需的动作",
        description="生成收敛计划但不修改系统；有待执行动作时返回 2。",
        examples="  dev-env plan\n  dev-env plan --json\n  dev-env plan --scope rustup",
    )
    plan.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="输出稳定的机器可读 JSON；不使用颜色",
    )
    plan.add_argument(
        "--scope",
        action="append",
        default=[],
        metavar="ADAPTER",
        help="只计划指定 adapter，可重复；当前可用: apt、mise、rustup",
    )

    apply = _command_parser(
        subparsers,
        "apply",
        help_text="确认后执行计划并刷新 inventory",
        description="先展示计划，只确认一次，然后安全收敛受管环境。",
        examples="  dev-env apply\n  dev-env apply --scope mise\n  dev-env apply --yes",
    )
    apply.add_argument("--yes", action="store_true", help="跳过交互确认，用于已审查计划的自动化执行")
    apply.add_argument(
        "--scope",
        action="append",
        default=[],
        metavar="ADAPTER",
        help="只收敛指定 adapter，可重复；当前可用: apt、mise、rustup",
    )

    add = _command_parser(
        subparsers,
        "add",
        help_text="声明并安装一个或多个软件",
        description=(
            "原子更新 mise.toml 中的 apt/mise 声明，展示计划并确认一次，然后安装并刷新 "
            "inventory；Rust 矩阵直接编辑 rustup.toml。"
        ),
        examples=(
            "  dev-env add apt:jq\n"
            "  dev-env add node@26 aqua:owner/tool@latest\n"
            "  dev-env add --yes npm:@scope/tool@latest"
        ),
    )
    add.add_argument("--yes", action="store_true", help="跳过交互确认，用于已审查声明和计划的自动化执行")
    add.add_argument(
        "specs",
        nargs="+",
        metavar="SPEC",
        help="apt:PACKAGE 或 mise 风格的 TOOL[@VERSION]",
    )

    _command_parser(
        subparsers,
        "inventory",
        help_text="更新结构化实际状态快照",
        description="只读探查环境，并原子更新 inventory/current.json。",
        examples="  dev-env inventory",
    )
    return parser


def _write_json(document: dict, stdout: TextIO) -> None:
    json.dump(document, stdout, ensure_ascii=False, indent=2, sort_keys=True)
    stdout.write("\n")


def _write_inventory_summary(document: dict, stdout: TextIO) -> None:
    summary = document["summary"]
    state = "converged" if summary["converged"] else "drift"
    line = f"state={state} missing={summary['missing']} extra={summary['extra']} findings={summary['findings']}"
    style = terminal_style(stdout)
    stdout.write(f"{style.green(line) if summary['converged'] else style.yellow(line)}\n")


def _write_plan_summary(document: dict, stdout: TextIO) -> None:
    style = terminal_style(stdout)
    for action in document["actions"]:
        stdout.write(
            f"{style.cyan(action['action'])} "
            f"{action['adapter']}:{action.get('kind', 'resource')} {action.get('name', '')}\n"
        )
    total = document["summary"]["total"]
    summary = f"total={total}"
    stdout.write(f"{style.bold_yellow(summary) if total else style.bold_green(summary)}\n")


def _write_declaration_summary(changes, stdout: TextIO) -> None:
    style = terminal_style(stdout)
    for change in changes:
        stdout.write(
            f"{style.cyan(change.action)} {change.adapter}:declaration {change.key}@{change.version}\n"
        )


def _write_result(state: str, stdout: TextIO) -> None:
    stdout.write(f"{terminal_style(stdout).green(f'result={state}')}\n")


def run(
    argv: Sequence[str],
    service,
    *,
    stdout: TextIO,
    stderr: TextIO,
    input_fn: Callable[[str], str] = input,
) -> int:
    args = _parser().parse_args(list(argv))

    try:
        if args.command in {"status", "check"}:
            document = service.inventory()
            if args.as_json:
                _write_json(document, stdout)
            else:
                _write_inventory_summary(document, stdout)
                write_manual_hint(stdout)
            if args.command == "check" and not document["summary"]["converged"]:
                return 2
            return 0

        if args.command == "plan":
            document = service.plan(args.scope)
            if args.as_json:
                _write_json(document, stdout)
            else:
                _write_plan_summary(document, stdout)
                write_manual_hint(stdout)
            return 2 if document["actions"] else 0

        if args.command == "inventory":
            path = service.write_inventory(INVENTORY_PATH)
            stdout.write(f"{terminal_style(stdout).green(f'inventory={path}')}\n")
            write_manual_hint(stdout)
            return 0

        if args.command == "add":
            transaction = service.prepare_add(args.specs)
            with transaction:
                _write_declaration_summary(transaction.changes, stdout)
                document = service.plan(transaction.scopes)
                _write_plan_summary(document, stdout)
                needs_confirmation = transaction.changed or bool(document["actions"])
                if not needs_confirmation:
                    service.write_inventory(INVENTORY_PATH, document=service.inventory())
                    _write_result("unchanged", stdout)
                    write_manual_hint(stdout)
                    return 0
                confirmed = args.yes
                if not confirmed:
                    confirmed = input_fn("Add these declarations and apply changes? [y/N] ").strip().lower() in {
                        "y",
                        "yes",
                    }
                if not confirmed:
                    write_error("add cancelled", stderr)
                    return 1

                transaction.retain()
                should_apply = bool(document["actions"]) or (
                    transaction.changed and "mise" in transaction.scopes
                )
                if should_apply:
                    try:
                        observed = service.apply(transaction.scopes, confirmed=True)
                    except BaseException:
                        try:
                            service.write_inventory(INVENTORY_PATH)
                        except Exception:
                            pass
                        raise
                else:
                    observed = service.inventory()
                service.write_inventory(INVENTORY_PATH, document=observed)
                _write_result("applied", stdout)
                write_manual_hint(stdout)
                return 0

        if args.command == "apply":
            document = service.plan(args.scope)
            _write_plan_summary(document, stdout)
            if not document["actions"]:
                service.write_inventory(INVENTORY_PATH)
                _write_result("converged", stdout)
                write_manual_hint(stdout)
                return 0
            confirmed = args.yes
            if not confirmed:
                confirmed = input_fn("Apply these changes? [y/N] ").strip().lower() in {"y", "yes"}
            if not confirmed:
                write_error("apply cancelled", stderr)
                return 1
            observed = service.apply(args.scope, confirmed=True)
            service.write_inventory(INVENTORY_PATH, document=observed)
            _write_result("applied", stdout)
            write_manual_hint(stdout)
            return 0
    except Exception as error:
        write_error(f"error: {error}", stderr)
        return 1

    return 1
