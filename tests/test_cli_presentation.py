import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.cli import run


class TtyBuffer(io.StringIO):
    def isatty(self):
        return True


class PresentationService:
    def __init__(self, *, converged=True, actions=(), error=None):
        self.error = error
        self.inventory_document = {
            "schema_version": 1,
            "platform": {"os": "ubuntu"},
            "adapters": {},
            "summary": {
                "converged": converged,
                "missing": 0 if converged else 1,
                "extra": 0,
                "findings": 0,
            },
        }
        self.plan_document = {
            "schema_version": 1,
            "actions": list(actions),
            "summary": {"total": len(actions)},
        }
        self.add_transaction = None

    def inventory(self):
        if self.error is not None:
            raise self.error
        return self.inventory_document

    def plan(self, scopes=()):
        if self.error is not None:
            raise self.error
        return self.plan_document

    def apply(self, scopes=(), *, confirmed=False):
        return self.inventory_document

    def write_inventory(self, path=None, *, document=None):
        return path or ROOT / "inventory" / "current.json"

    def prepare_add(self, specs):
        return self.add_transaction


class PresentationTransaction:
    def __init__(self, *, changed=True, changes=(), scopes=("mise",)):
        self.changed = changed
        self.changes = tuple(changes)
        self.scopes = tuple(scopes)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def retain(self):
        pass


class CliPresentationTests(unittest.TestCase):
    def render_help(self, *arguments):
        output = io.StringIO()
        with self.assertRaises(SystemExit) as raised:
            with redirect_stdout(output):
                run([*arguments, "--help"], None, stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(0, raised.exception.code)
        return output.getvalue()

    def test_main_help_explains_commands_and_points_to_manual(self):
        output = self.render_help()

        self.assertIn("查看、比较并收敛 WSL2 开发环境", output)
        self.assertIn("status", output)
        self.assertIn("查看当前环境摘要", output)
        self.assertIn("完整操作手册: docs/operations.md", output)

    def test_subcommand_help_explains_options_and_includes_examples(self):
        status_help = self.render_help("status")
        apply_help = self.render_help("apply")
        add_help = self.render_help("add")

        self.assertIn("输出稳定的机器可读 JSON；不使用颜色", status_help)
        self.assertIn("当前可用: apt、mise、rustup", apply_help)
        self.assertIn("示例:", apply_help)
        self.assertIn("dev-env apply --scope mise", apply_help)
        self.assertIn("rustup.toml", add_help)
        self.assertIn("完整操作手册: docs/operations.md", apply_help)

    def test_tty_status_uses_green_for_converged_summary_and_ends_with_manual_hint(self):
        stdout = TtyBuffer()
        with patch.dict(os.environ, {}, clear=True):
            result = run(
                ["status"],
                PresentationService(converged=True),
                stdout=stdout,
                stderr=TtyBuffer(),
            )

        self.assertEqual(0, result)
        self.assertIn("\x1b[32mstate=converged", stdout.getvalue())
        self.assertEqual("详细操作见: docs/operations.md", stdout.getvalue().splitlines()[-1])

    def test_tty_status_uses_yellow_for_drift(self):
        stdout = TtyBuffer()
        with patch.dict(os.environ, {}, clear=True):
            run(
                ["status"],
                PresentationService(converged=False),
                stdout=stdout,
                stderr=TtyBuffer(),
            )

        self.assertIn("\x1b[33mstate=drift", stdout.getvalue())

    def test_tty_plan_distinguishes_actions_and_bold_summary(self):
        stdout = TtyBuffer()
        service = PresentationService(
            actions=({"adapter": "apt", "kind": "package", "action": "create", "name": "apt:jq"},)
        )
        with patch.dict(os.environ, {}, clear=True):
            result = run(["plan"], service, stdout=stdout, stderr=TtyBuffer())

        self.assertEqual(2, result)
        self.assertIn("\x1b[36mcreate\x1b[0m", stdout.getvalue())
        self.assertIn("\x1b[1;33mtotal=1\x1b[0m", stdout.getvalue())
        self.assertEqual("详细操作见: docs/operations.md", stdout.getvalue().splitlines()[-1])

    def test_no_color_disables_ansi_even_for_tty(self):
        stdout = TtyBuffer()
        with patch.dict(os.environ, {"NO_COLOR": ""}, clear=True):
            run(
                ["status"],
                PresentationService(converged=True),
                stdout=stdout,
                stderr=TtyBuffer(),
            )

        self.assertNotIn("\x1b[", stdout.getvalue())

    def test_json_output_never_contains_ansi_or_manual_hint(self):
        stdout = TtyBuffer()
        with patch.dict(os.environ, {}, clear=True):
            result = run(
                ["status", "--json"],
                PresentationService(converged=True),
                stdout=stdout,
                stderr=TtyBuffer(),
            )

        self.assertEqual(0, result)
        self.assertNotIn("\x1b[", stdout.getvalue())
        self.assertNotIn("详细操作见", stdout.getvalue())
        self.assertTrue(json.loads(stdout.getvalue())["summary"]["converged"])

    def test_tty_error_is_red_and_ends_with_manual_hint(self):
        stderr = TtyBuffer()
        with patch.dict(os.environ, {}, clear=True):
            result = run(
                ["status"],
                PresentationService(error=RuntimeError("boom")),
                stdout=TtyBuffer(),
                stderr=stderr,
            )

        self.assertEqual(1, result)
        self.assertIn("\x1b[31merror: boom\x1b[0m", stderr.getvalue())
        self.assertEqual("详细操作见: docs/operations.md", stderr.getvalue().splitlines()[-1])

    def test_tty_inventory_uses_green_summary_and_ends_with_manual_hint(self):
        stdout = TtyBuffer()
        with patch.dict(os.environ, {}, clear=True):
            result = run(
                ["inventory"],
                PresentationService(),
                stdout=stdout,
                stderr=TtyBuffer(),
            )

        self.assertEqual(0, result)
        self.assertIn("\x1b[32minventory=", stdout.getvalue())
        self.assertEqual("详细操作见: docs/operations.md", stdout.getvalue().splitlines()[-1])

    def test_tty_apply_reports_converged_result_and_ends_with_manual_hint(self):
        stdout = TtyBuffer()
        with patch.dict(os.environ, {}, clear=True):
            result = run(
                ["apply", "--yes"],
                PresentationService(actions=()),
                stdout=stdout,
                stderr=TtyBuffer(),
            )

        self.assertEqual(0, result)
        self.assertIn("\x1b[32mresult=converged\x1b[0m", stdout.getvalue())
        self.assertEqual("详细操作见: docs/operations.md", stdout.getvalue().splitlines()[-1])

    def test_tty_add_colors_declaration_and_reports_applied_result(self):
        stdout = TtyBuffer()
        service = PresentationService(
            actions=({"adapter": "mise", "kind": "tool", "action": "create", "name": "node@26"},)
        )
        service.add_transaction = PresentationTransaction(
            changes=(SimpleNamespace(action="add", adapter="mise", key="node", version="26"),)
        )
        with patch.dict(os.environ, {}, clear=True):
            result = run(
                ["add", "--yes", "node@26"],
                service,
                stdout=stdout,
                stderr=TtyBuffer(),
            )

        self.assertEqual(0, result)
        self.assertIn("\x1b[36madd\x1b[0m mise:declaration node@26", stdout.getvalue())
        self.assertIn("\x1b[32mresult=applied\x1b[0m", stdout.getvalue())
        self.assertEqual("详细操作见: docs/operations.md", stdout.getvalue().splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
