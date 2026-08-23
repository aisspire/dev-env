import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.backend import MiseBackend


class FakeRunner:
    def __init__(self):
        self.json_commands = []
        self.interactive_commands = []

    def run_json(self, command, *, cwd=None, env=None):
        self.json_commands.append((command, cwd, env))
        if "status" in command:
            return {"packages": {}, "tools": []}
        if "plan" in command:
            return {"resources": [], "summary": {}}
        return {}

    def run_interactive(self, command, *, cwd=None, env=None):
        self.interactive_commands.append((command, cwd, env))


class MiseBackendTests(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.backend = MiseBackend(ROOT, self.runner, mise_binary="/usr/bin/mise")

    def test_reads_native_json_from_repository_config_root(self):
        self.backend.status()
        self.backend.plan()
        self.backend.installed_tools()

        commands = [(command, cwd) for command, cwd, _ in self.runner.json_commands]
        self.assertEqual(
            [
                (["/usr/bin/mise", "-C", str(ROOT), "bootstrap", "status", "--json"], ROOT),
                (["/usr/bin/mise", "-C", str(ROOT), "bootstrap", "plan", "--json"], ROOT),
                (["/usr/bin/mise", "-C", str(ROOT), "ls", "--installed", "--json"], ROOT),
            ],
            commands,
        )
        for _, _, env in self.runner.json_commands:
            self.assertIn(str(ROOT), env["MISE_TRUSTED_CONFIG_PATHS"])

    def test_applies_only_apt_resources(self):
        self.backend.apply(("apt",), confirmed=True)

        self.assertEqual(
            [
                (
                    ["/usr/bin/mise", "-C", str(ROOT), "bootstrap", "--only", "packages", "--yes"],
                    ROOT,
                    unittest.mock.ANY,
                )
            ],
            self.runner.interactive_commands,
        )

    def test_applies_only_mise_resources(self):
        self.backend.apply(("mise",), confirmed=False)

        self.assertEqual(
            [
                (
                    [
                        "/usr/bin/mise",
                        "-C",
                        str(ROOT),
                        "bootstrap",
                        "--only",
                        "dotfiles,mise-shell-activate,tools",
                    ],
                    ROOT,
                    unittest.mock.ANY,
                )
            ],
            self.runner.interactive_commands,
        )


if __name__ == "__main__":
    unittest.main()
