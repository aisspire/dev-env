import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.normalize import normalize_inventory, normalize_plan


BOOTSTRAP_STATUS = {
    "packages": {
        "apt": {
            "available": True,
            "packages": [
                {
                    "package": "ca-certificates",
                    "requested_version": "latest",
                    "state": "installed",
                    "installed_version": "20260601~26.04.1",
                },
                {
                    "package": "jq",
                    "requested_version": "latest",
                    "state": "missing",
                    "installed_version": "",
                },
            ],
        }
    },
    "dotfiles": {
        "files": [
            {
                "target": "~/.config/mise/config.toml",
                "source": "/workspace/mise.toml",
                "mode": "symlink",
                "state": "missing",
            }
        ],
        "edits": [],
    },
    "mise_shell_activate": [
        {
            "target": "bashrc",
            "shell": "bash",
            "path": "~/.bashrc",
            "mode": "activate",
            "state": "missing",
        }
    ],
    "tools": [
        {
            "tool": "java",
            "requested_version": "temurin-21",
            "resolved_version": "temurin-21.0.8+9",
            "state": "missing",
            "installed": False,
        },
        {
            "tool": "python",
            "requested_version": "3.12",
            "resolved_version": "3.12.14",
            "state": "installed",
            "installed": True,
        },
    ],
}

INSTALLED_TOOLS = {
    "java": [
        {
            "version": "21.0.2",
            "install_path": "/home/example/.local/share/mise/installs/java/21.0.2",
            "installed": True,
            "active": False,
        }
    ],
    "node": [
        {
            "version": "22.23.2",
            "install_path": "/home/example/.local/share/mise/installs/node/22.23.2",
            "installed": True,
            "active": False,
        }
    ],
    "python": [
        {
            "version": "3.12.14",
            "install_path": "/home/example/.local/share/mise/installs/python/3.12.14",
            "installed": True,
            "active": False,
        }
    ],
}

BOOTSTRAP_PLAN = {
    "resources": [
        {
            "id": {"kind": "package", "name": "apt:ca-certificates"},
            "current": "installed (20260601~26.04.1)",
            "desired": "installed (any version)",
            "action": "noop",
        },
        {
            "id": {"kind": "package", "name": "apt:jq"},
            "current": "missing",
            "desired": "installed (any version)",
            "action": "create",
        },
    ],
    "summary": {"create": 1, "update": 0, "remove": 0, "unchanged": 1, "unknown": 0},
}


class NormalizeInventoryTests(unittest.TestCase):
    def test_normalizes_missing_and_extra_without_host_paths(self):
        platform = {
            "os": "ubuntu",
            "version": "26.04",
            "architecture": "x86_64",
            "wsl": True,
            "init": "systemd",
        }

        result = normalize_inventory(platform, BOOTSTRAP_STATUS, INSTALLED_TOOLS)

        self.assertEqual(1, result["schema_version"])
        self.assertEqual("drift", result["adapters"]["apt"]["status"])
        self.assertEqual([{"name": "jq", "requested_version": "latest"}], result["adapters"]["apt"]["missing"])
        self.assertEqual("drift", result["adapters"]["mise"]["status"])
        self.assertEqual(
            [{"tool": "java", "requested_version": "temurin-21", "resolved_version": "temurin-21.0.8+9"}],
            result["adapters"]["mise"]["missing"],
        )
        self.assertEqual(
            [
                {"tool": "java", "version": "21.0.2"},
                {"tool": "node", "version": "22.23.2"},
            ],
            result["adapters"]["mise"]["extra"],
        )
        self.assertNotIn("install_path", str(result))
        self.assertFalse(result["summary"]["converged"])
        self.assertEqual(2, result["summary"]["missing"])
        self.assertEqual(2, result["summary"]["extra"])
        self.assertEqual(2, result["summary"]["findings"])
        self.assertEqual(
            ["mise.dotfile.missing", "mise.shell_activation.missing"],
            [finding["code"] for finding in result["adapters"]["mise"]["findings"]],
        )

    def test_extra_tools_are_warnings_not_drift(self):
        status = {
            "packages": {"apt": {"available": True, "packages": []}},
            "mise_shell_activate": [],
            "tools": [],
        }

        result = normalize_inventory({}, status, INSTALLED_TOOLS)

        self.assertEqual("converged", result["adapters"]["mise"]["status"])
        self.assertTrue(result["summary"]["converged"])
        self.assertEqual(3, result["summary"]["extra"])


class NormalizePlanTests(unittest.TestCase):
    def test_combines_native_resources_with_missing_tools_and_shell(self):
        result = normalize_plan(BOOTSTRAP_STATUS, BOOTSTRAP_PLAN)

        self.assertEqual(
            [
                {
                    "adapter": "apt",
                    "kind": "package",
                    "name": "apt:jq",
                    "action": "create",
                    "current": "missing",
                    "desired": "installed (any version)",
                },
                {
                    "adapter": "mise",
                    "kind": "dotfile",
                    "name": "~/.config/mise/config.toml",
                    "action": "repair",
                    "current": "missing",
                    "desired": "symlink",
                },
                {
                    "adapter": "mise",
                    "kind": "shell_activation",
                    "name": "bashrc",
                    "action": "repair",
                    "current": "missing",
                    "desired": "activate",
                },
                {
                    "adapter": "mise",
                    "kind": "tool",
                    "name": "java@temurin-21",
                    "action": "create",
                    "current": "missing",
                    "desired": "temurin-21.0.8+9",
                },
            ],
            result["actions"],
        )
        self.assertEqual({"create": 2, "repair": 2, "total": 4}, result["summary"])
        self.assertNotIn("remove", [action["action"] for action in result["actions"]])


if __name__ == "__main__":
    unittest.main()
