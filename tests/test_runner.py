import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.runner import CommandError, CommandRunner


class CommandRunnerTests(unittest.TestCase):
    def test_parses_json_without_using_a_shell(self):
        runner = CommandRunner()

        result = runner.run_json(["/usr/bin/python3", "-c", 'import json; print(json.dumps({"ok": True}))'])

        self.assertEqual({"ok": True}, result)

    def test_reports_stderr_and_exit_code(self):
        runner = CommandRunner()

        with self.assertRaises(CommandError) as caught:
            runner.run_json(["/usr/bin/python3", "-c", 'import sys; print("broken", file=sys.stderr); raise SystemExit(7)'])

        self.assertEqual(7, caught.exception.returncode)
        self.assertIn("broken", str(caught.exception))

    def test_rejects_invalid_json(self):
        runner = CommandRunner()

        with self.assertRaises(CommandError) as caught:
            runner.run_json(["/usr/bin/python3", "-c", 'print("not-json")'])

        self.assertIn("invalid JSON", str(caught.exception))

    def test_interactive_command_inherits_standard_streams(self):
        runner = CommandRunner()

        completed = runner.run_interactive(["/usr/bin/python3", "-c", "pass"])

        self.assertEqual(0, completed.returncode)


if __name__ == "__main__":
    unittest.main()
