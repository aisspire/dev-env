import json
import sys
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class WorkstationConfigTests(unittest.TestCase):
    def setUp(self):
        with (ROOT / "mise.toml").open("rb") as config_file:
            self.config = tomllib.load(config_file)

    def test_apt_manifest_has_one_machine_readable_source(self):
        self.assertTrue(
            {
                "apt:build-essential",
                "apt:ca-certificates",
                "apt:curl",
                "apt:git",
                "apt:libbz2-dev",
                "apt:libffi-dev",
                "apt:liblzma-dev",
                "apt:libncurses-dev",
                "apt:libreadline-dev",
                "apt:libsqlite3-dev",
                "apt:libssl-dev",
                "apt:mise",
                "apt:zlib1g-dev",
            }.issubset(self.config["bootstrap"]["packages"]),
        )

    def test_runtime_intent_and_defaults_are_ordered(self):
        self.assertEqual(["3.12", "3.11", "3.10", "3.9", "3.8"], self.config["tools"]["python"][:5])
        self.assertEqual(["22", "20", "24"], self.config["tools"]["node"][:3])
        self.assertEqual(["temurin-21", "temurin-17"], self.config["tools"]["java"][:2])

    def test_lock_shell_and_global_links_are_declared(self):
        self.assertTrue(self.config["settings"]["lockfile"])
        self.assertEqual("activate", self.config["bootstrap"]["mise_shell_activate"]["bashrc"])
        self.assertEqual(
            "config/shell/bash_aliases",
            self.config["dotfiles"]["~/.bash_aliases"]["source"],
        )
        self.assertEqual("mise.toml", self.config["dotfiles"]["~/.config/mise/config.toml"]["source"])
        self.assertEqual("mise.lock", self.config["dotfiles"]["~/.config/mise/mise.lock"]["source"])

    def test_standard_rust_homes_and_cargo_bin_path_are_declared(self):
        self.assertEqual("{{env.HOME}}/.cargo", self.config["env"]["CARGO_HOME"])
        self.assertEqual("{{env.HOME}}/.rustup", self.config["env"]["RUSTUP_HOME"])
        self.assertEqual(["{{env.HOME}}/.cargo/bin"], self.config["env"]["_"]["path"])

    def test_lockfile_pins_every_declared_tool_for_linux_x64(self):
        with (ROOT / "mise.lock").open("rb") as lock_file:
            lock = tomllib.load(lock_file)

        versions = {
            tool: {entry["version"] for entry in entries}
            for tool, entries in lock["tools"].items()
        }
        for tool, requested in self.config["tools"].items():
            requested_versions = requested if isinstance(requested, list) else [requested]
            self.assertIn(tool, versions)
            for requested_version in requested_versions:
                if requested_version == "latest":
                    self.assertTrue(versions[tool])
                else:
                    self.assertTrue(
                        any(
                            version == requested_version
                            or version.startswith(f"{requested_version}.")
                            or version.startswith(f"{requested_version}+")
                            for version in versions[tool]
                        ),
                        f"{tool}@{requested_version} is not represented in mise.lock",
                    )
        for entries in lock["tools"].values():
            for entry in entries:
                platform = entry["platforms.linux-x64"]
                self.assertTrue(platform["url"].startswith("https://"))
                self.assertTrue(platform["checksum"].startswith("sha256:"))

    def test_public_inventory_example_is_fictional_and_current_is_ignored(self):
        with (ROOT / "inventory" / "example.json").open(encoding="utf-8") as example_file:
            example = json.load(example_file)

        self.assertEqual(1, example["schema_version"])
        self.assertTrue(example["summary"]["converged"])
        self.assertIn("example", json.dumps(example, sort_keys=True))

        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("/inventory/current.json", ignored)
        self.assertIn("/docs/doing.md", ignored)
        self.assertIn("/docs/sessions/", ignored)


if __name__ == "__main__":
    unittest.main()
