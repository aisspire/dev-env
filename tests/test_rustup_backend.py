import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.runner import CommandError
from dev_env.rustup_backend import RUSTUP_DIST_ROOT, RustupBackend, RustupError


HOST = "x86_64-unknown-linux-gnu"
CONFIG = """schema_version = 1
default_toolchain = "stable"
profile = "minimal"

[toolchains.stable]
components = ["clippy", "rust-analyzer", "rustfmt"]
targets = []

[toolchains.nightly]
components = ["clippy", "rust-analyzer", "rustfmt"]
targets = []
"""


class FakeRunner:
    def __init__(self, outputs=None):
        self.outputs = dict(outputs or {})
        self.read_commands = []
        self.interactive_commands = []
        self.fail_interactive = set()
        self.interactive_hook = None

    def run(self, command, *, cwd=None, env=None):
        command = list(command)
        self.read_commands.append((command, cwd, env))
        key = tuple(command[1:])
        if key not in self.outputs:
            raise CommandError(tuple(command), 1, f"unexpected read command: {key}")
        return SimpleNamespace(returncode=0, stdout=self.outputs[key], stderr="")

    def run_interactive(self, command, *, cwd=None, env=None):
        command = list(command)
        self.interactive_commands.append((command, cwd, env))
        if self.interactive_hook is not None:
            self.interactive_hook(command, cwd, env)
        key = tuple(command[1:])
        if key in self.fail_interactive:
            raise CommandError(tuple(command), 1, "simulated rustup failure")
        return SimpleNamespace(returncode=0)


class RustupBackendTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.repo_root = self.workspace / "repo"
        self.cargo_home = self.workspace / "cargo-home"
        self.rustup_home = self.workspace / "rustup-home"
        self.repo_root.mkdir()
        self.rustup_home.mkdir()
        (self.repo_root / "rustup.toml").write_text(CONFIG, encoding="utf-8")

    def write_settings(self, *, profile="minimal", default=f"stable-{HOST}"):
        lines = [f'profile = "{profile}"']
        if default is not None:
            lines.append(f'default_toolchain = "{default}"')
        (self.rustup_home / "settings.toml").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    def backend(
        self,
        runner,
        *,
        rustup_binary="/fake/rustup",
        binary_finder=None,
        architecture_probe=lambda: "x86_64",
        downloader=lambda url: b"",
    ):
        return RustupBackend(
            self.repo_root,
            runner,
            rustup_binary=rustup_binary,
            cargo_home=self.cargo_home,
            rustup_home=self.rustup_home,
            env={"PATH": ""},
            binary_finder=binary_finder or (lambda name: None),
            architecture_probe=architecture_probe,
            downloader=downloader,
        )

    def snapshot_outputs(
        self,
        *,
        stable_components=("cargo", "clippy", "rust-analyzer", "rust-std", "rustc", "rustfmt"),
        nightly_components=("cargo", "clippy", "rust-analyzer", "rust-std", "rustc", "rustfmt"),
        include_extras=False,
    ):
        rows = [f"stable-{HOST} (active, default)", f"nightly-{HOST}"]
        if include_extras:
            rows.append(f"1.80.0-{HOST}")
        outputs = {
            ("--version",): "rustup 1.29.0 (d243d7d4e 2026-03-04)\n",
            ("toolchain", "list"): "\n".join(rows) + "\n",
            ("show",): f"Default host: {HOST}\nrustup home: ignored\n",
            (
                "run",
                f"stable-{HOST}",
                "rustc",
                "--version",
                "--verbose",
            ): (
                "rustc 1.91.0 (f8297e351 2026-08-06)\n"
                "binary: rustc\n"
                "commit-hash: f8297e351\n"
                "commit-date: 2026-08-06\n"
                f"host: {HOST}\n"
                "release: 1.91.0\n"
            ),
            (
                "component",
                "list",
                "--installed",
                "--toolchain",
                f"stable-{HOST}",
            ): "\n".join(
                name if name == "rust-src" else f"{name}-{HOST}"
                for name in stable_components
            )
            + "\n"
            + ("rust-std-wasm32-unknown-unknown\n" if include_extras else ""),
            (
                "target",
                "list",
                "--installed",
                "--toolchain",
                f"stable-{HOST}",
            ): f"{HOST}\n"
            + ("wasm32-unknown-unknown\n" if include_extras else ""),
            (
                "run",
                f"nightly-{HOST}",
                "rustc",
                "--version",
                "--verbose",
            ): (
                "rustc 1.93.0-nightly (5adf3c5f0 2026-08-22)\n"
                "binary: rustc\n"
                "commit-hash: 5adf3c5f0\n"
                "commit-date: 2026-08-22\n"
                f"host: {HOST}\n"
                "release: 1.93.0-nightly\n"
            ),
            (
                "component",
                "list",
                "--installed",
                "--toolchain",
                f"nightly-{HOST}",
            ): "\n".join(f"{name}-{HOST}" for name in nightly_components) + "\n",
            (
                "target",
                "list",
                "--installed",
                "--toolchain",
                f"nightly-{HOST}",
            ): f"{HOST}\n",
        }
        if include_extras:
            outputs.update(
                {
                    (
                        "run",
                        f"1.80.0-{HOST}",
                        "rustc",
                        "--version",
                        "--verbose",
                    ): (
                        "rustc 1.80.0 (051478957 2024-07-21)\n"
                        "commit-date: 2024-07-21\n"
                        f"host: {HOST}\n"
                        "release: 1.80.0\n"
                    ),
                    (
                        "component",
                        "list",
                        "--installed",
                        "--toolchain",
                        f"1.80.0-{HOST}",
                    ): f"cargo-{HOST}\nrust-std-{HOST}\nrustc-{HOST}\n",
                    (
                        "target",
                        "list",
                        "--installed",
                        "--toolchain",
                        f"1.80.0-{HOST}",
                    ): f"{HOST}\n",
                }
            )
        return outputs

    def test_parses_exact_releases_and_reports_extras_without_drift_or_paths(self):
        self.write_settings()
        outputs = self.snapshot_outputs(
            stable_components=(
                "cargo",
                "clippy",
                "rust-analyzer",
                "rust-src",
                "rust-std",
                "rustc",
                "rustfmt",
            ),
            include_extras=True,
        )
        runner = FakeRunner(outputs)
        backend = self.backend(runner)

        first = backend.status()
        second = backend.status()

        self.assertEqual(first, second)
        self.assertEqual("converged", first["status"])
        self.assertEqual({"version": "1.29.0"}, first["manager"])
        self.assertEqual("stable", first["default_toolchain"]["observed"])
        self.assertEqual([], first["missing"])
        self.assertEqual([], first["findings"])
        self.assertIn(
            {"kind": "component", "toolchain": "stable", "name": "rust-src"},
            first["extra"],
        )
        self.assertIn(
            {"kind": "target", "toolchain": "stable", "name": "wasm32-unknown-unknown"},
            first["extra"],
        )
        self.assertNotIn(
            {
                "kind": "component",
                "toolchain": "stable",
                "name": "rust-std-wasm32-unknown-unknown",
            },
            first["extra"],
        )
        self.assertIn({"kind": "toolchain", "toolchain": "1.80.0"}, first["extra"])
        stable = next(item for item in first["observed"] if item["toolchain"] == "stable")
        nightly = next(item for item in first["observed"] if item["toolchain"] == "nightly")
        self.assertEqual(("1.91.0", "2026-08-06"), (stable["release"], stable["commit_date"]))
        self.assertEqual(
            ("1.93.0-nightly", "2026-08-22"),
            (nightly["release"], nightly["commit_date"]),
        )
        rendered = json.dumps(first, sort_keys=True)
        self.assertNotIn(str(self.workspace), rendered)
        self.assertNotIn("rustup home", rendered)

    def test_missing_manager_plan_is_read_only_and_has_only_create_or_repair(self):
        downloads = []
        runner = FakeRunner()
        backend = self.backend(
            runner,
            rustup_binary=None,
            binary_finder=lambda name: None,
            downloader=lambda url: downloads.append(url) or b"",
        )

        state = backend.status()
        actions = backend.plan()

        self.assertFalse(state["available"])
        self.assertEqual([], runner.read_commands)
        self.assertEqual([], runner.interactive_commands)
        self.assertEqual([], downloads)
        self.assertEqual(
            {"manager", "profile", "toolchain", "default_toolchain"},
            {action["kind"] for action in actions},
        )
        self.assertLessEqual({action["action"] for action in actions}, {"create", "repair"})

    def test_profile_and_default_mismatches_plan_repairs_without_updates_or_removals(self):
        self.write_settings(profile="default", default=f"nightly-{HOST}")
        runner = FakeRunner(self.snapshot_outputs())
        backend = self.backend(runner)

        actions = backend.plan()

        self.assertEqual(
            {("profile", "repair"), ("default_toolchain", "repair")},
            {(action["kind"], action["action"]) for action in actions},
        )
        self.assertNotIn("update", {action["action"] for action in actions})
        self.assertNotIn("remove", {action["action"] for action in actions})

    def test_installs_default_stable_before_setting_default_and_then_nightly(self):
        self.write_settings(default=None)
        runner = FakeRunner(
            {
                ("--version",): "rustup 1.29.0 (d243d7d4e 2026-03-04)\n",
                ("toolchain", "list"): "no installed toolchains\n",
                ("show",): f"Default host: {HOST}\n",
            }
        )
        backend = self.backend(runner)

        backend.apply(confirmed=True)

        commands = [command for command, _, _ in runner.interactive_commands]
        self.assertEqual("stable", commands[0][3])
        self.assertEqual(["/fake/rustup", "default", "stable"], commands[1])
        self.assertEqual("nightly", commands[2][3])
        self.assertIn("--no-self-update", commands[0])
        self.assertIn("--no-self-update", commands[2])
        self.assertNotIn("--allow-downgrade", commands[0])
        self.assertIn("--allow-downgrade", commands[2])

    def test_existing_toolchains_only_receive_missing_components(self):
        self.write_settings()
        components = ("cargo", "clippy", "rust-std", "rustc", "rustfmt")
        runner = FakeRunner(
            self.snapshot_outputs(
                stable_components=components,
                nightly_components=components,
            )
        )
        backend = self.backend(runner)

        backend.apply(confirmed=True)

        commands = [command for command, _, _ in runner.interactive_commands]
        self.assertEqual(
            [
                [
                    "/fake/rustup",
                    "component",
                    "add",
                    "rust-analyzer",
                    "--toolchain",
                    "stable",
                ],
                [
                    "/fake/rustup",
                    "component",
                    "add",
                    "rust-analyzer",
                    "--toolchain",
                    "nightly",
                ],
            ],
            commands,
        )
        self.assertFalse(any(command[1:3] == ["toolchain", "install"] for command in commands))

    def test_existing_toolchain_only_receives_declared_missing_target(self):
        config = CONFIG.replace(
            "targets = []",
            'targets = ["wasm32-unknown-unknown"]',
            1,
        )
        (self.repo_root / "rustup.toml").write_text(config, encoding="utf-8")
        self.write_settings()
        runner = FakeRunner(self.snapshot_outputs())
        backend = self.backend(runner)

        backend.apply(confirmed=True)

        commands = [command for command, _, _ in runner.interactive_commands]
        self.assertEqual(
            [
                [
                    "/fake/rustup",
                    "target",
                    "add",
                    "wasm32-unknown-unknown",
                    "--toolchain",
                    "stable",
                ]
            ],
            commands,
        )

    def test_apply_repairs_profile_and_default_without_reinstalling_toolchains(self):
        self.write_settings(profile="default", default=f"nightly-{HOST}")
        runner = FakeRunner(self.snapshot_outputs())
        backend = self.backend(runner)

        backend.apply(confirmed=True)

        commands = [command for command, _, _ in runner.interactive_commands]
        self.assertEqual(
            [
                ["/fake/rustup", "set", "profile", "minimal"],
                ["/fake/rustup", "default", "stable"],
            ],
            commands,
        )
        self.assertFalse(any(command[1:3] == ["toolchain", "install"] for command in commands))

    def test_unavailable_component_on_existing_nightly_fails_without_switching_snapshot(self):
        self.write_settings()
        nightly_components = ("cargo", "clippy", "rust-std", "rustc", "rustfmt")
        runner = FakeRunner(self.snapshot_outputs(nightly_components=nightly_components))
        runner.fail_interactive.add(
            ("component", "add", "rust-analyzer", "--toolchain", "nightly")
        )
        backend = self.backend(runner)

        with self.assertRaises(CommandError):
            backend.apply(confirmed=True)

        commands = [command for command, _, _ in runner.interactive_commands]
        self.assertEqual(
            [
                "/fake/rustup",
                "component",
                "add",
                "rust-analyzer",
                "--toolchain",
                "nightly",
            ],
            commands[-1],
        )
        self.assertFalse(any("--allow-downgrade" in command for command in commands))
        self.assertFalse(any(command[1:3] == ["toolchain", "install"] for command in commands))
        self.assertEqual("drift", backend.status()["status"])

    def test_sha_mismatch_stops_before_executing_installer(self):
        downloads = []

        def download(url):
            downloads.append(url)
            return b"0" * 64 if url.endswith(".sha256") else b"installer payload"

        runner = FakeRunner()
        backend = self.backend(
            runner,
            rustup_binary=None,
            binary_finder=lambda name: None,
            downloader=download,
        )

        with self.assertRaisesRegex(RustupError, "SHA256 mismatch"):
            backend.apply(confirmed=True)

        self.assertEqual(2, len(downloads))
        self.assertEqual([], runner.interactive_commands)

    def test_unknown_architecture_and_foreign_rust_conflict_fail_before_download(self):
        for architecture, finder, message in (
            ("riscv64", lambda name: None, "unsupported architecture"),
            (
                "x86_64",
                lambda name: "/usr/bin/rustc" if name == "rustc" else None,
                "not owned by rustup",
            ),
        ):
            with self.subTest(message=message):
                downloads = []
                runner = FakeRunner()
                backend = self.backend(
                    runner,
                    rustup_binary=None,
                    binary_finder=finder,
                    architecture_probe=lambda value=architecture: value,
                    downloader=lambda url: downloads.append(url) or b"",
                )

                with self.assertRaisesRegex(RustupError, message):
                    backend.apply(confirmed=True)

                self.assertEqual([], downloads)
                self.assertEqual([], runner.interactive_commands)

    def test_verified_installer_runs_directly_with_no_path_modification(self):
        payload = b"simulated official rustup-init"
        checksum = hashlib.sha256(payload).hexdigest().encode("ascii") + b"  rustup-init\n"
        urls = []

        def download(url):
            urls.append(url)
            return checksum if url.endswith(".sha256") else payload

        runner = FakeRunner()

        def create_installed_binary(command, cwd, env):
            installed = self.cargo_home / "bin" / "rustup"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(b"rustup")
            installed.chmod(0o700)

        runner.interactive_hook = create_installed_binary
        backend = self.backend(
            runner,
            rustup_binary=None,
            binary_finder=lambda name: None,
            downloader=download,
        )

        backend._install_manager("minimal", HOST)

        self.assertEqual(
            [
                f"{RUSTUP_DIST_ROOT}/{HOST}/rustup-init",
                f"{RUSTUP_DIST_ROOT}/{HOST}/rustup-init.sha256",
            ],
            urls,
        )
        command, cwd, env = runner.interactive_commands[0]
        self.assertTrue(command[0].endswith("/rustup-init"))
        self.assertEqual(
            [
                "-y",
                "--no-modify-path",
                "--default-toolchain",
                "none",
                "--profile",
                "minimal",
            ],
            command[1:],
        )
        self.assertEqual(self.repo_root, cwd)
        self.assertEqual(str(self.cargo_home), env["CARGO_HOME"])
        self.assertEqual(str(self.rustup_home), env["RUSTUP_HOME"])

    def test_installer_architecture_mapping_supports_wsl_native_architectures(self):
        for architecture, expected in (
            ("x86_64", "x86_64-unknown-linux-gnu"),
            ("aarch64", "aarch64-unknown-linux-gnu"),
        ):
            backend = self.backend(
                FakeRunner(),
                rustup_binary=None,
                architecture_probe=lambda value=architecture: value,
            )
            with self.subTest(architecture=architecture):
                self.assertEqual(expected, backend._installer_target())


if __name__ == "__main__":
    unittest.main()
