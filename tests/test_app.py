import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.app import build_service, main


class TtyBuffer(io.StringIO):
    def isatty(self):
        return True


class AppTests(unittest.TestCase):
    def test_build_service_uses_requested_mise_binary(self):
        service = build_service(
            ROOT,
            mise_binary="/custom/mise",
            rustup_binary="/custom/rustup",
        )

        self.assertEqual("/custom/mise", service.backend.mise_binary)
        self.assertEqual("/custom/rustup", service.rustup_backend._configured_binary)

    def test_main_explains_how_to_bootstrap_when_mise_is_missing(self):
        stderr = io.StringIO()
        with patch("dev_env.app.shutil.which", return_value=None):
            result = main(["status"], stdout=io.StringIO(), stderr=stderr)

        self.assertEqual(1, result)
        self.assertIn("scripts/bootstrap", stderr.getvalue())
        self.assertIn("mise", stderr.getvalue())

    def test_main_help_is_available_when_mise_is_missing(self):
        stdout = io.StringIO()
        with patch("dev_env.app.shutil.which", return_value=None):
            result = main(["--help"], stdout=stdout, stderr=io.StringIO())

        self.assertEqual(0, result)
        self.assertIn("查看、比较并收敛 WSL2 开发环境", stdout.getvalue())
        self.assertIn("完整操作手册: docs/operations.md", stdout.getvalue())

    def test_missing_mise_error_is_red_on_tty_and_points_to_manual(self):
        stderr = TtyBuffer()
        with patch.dict(os.environ, {}, clear=True):
            with patch("dev_env.app.shutil.which", return_value=None):
                result = main(["status"], stdout=TtyBuffer(), stderr=stderr)

        self.assertEqual(1, result)
        self.assertIn("\x1b[31merror: mise is not installed", stderr.getvalue())
        self.assertEqual("详细操作见: docs/operations.md", stderr.getvalue().splitlines()[-1])

    def test_bare_command_reports_usage_before_checking_for_mise(self):
        stderr = io.StringIO()
        with patch("dev_env.app.shutil.which", return_value=None):
            result = main([], stdout=io.StringIO(), stderr=stderr)

        self.assertEqual(2, result)
        self.assertIn("usage: dev-env", stderr.getvalue())
        self.assertIn("the following arguments are required: COMMAND", stderr.getvalue())
        self.assertEqual("详细操作见: docs/operations.md", stderr.getvalue().splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
