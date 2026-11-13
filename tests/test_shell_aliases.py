import os
import shlex
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL_CONFIG = ROOT / "config" / "shell" / "bash_aliases"


class ShellAliasesTests(unittest.TestCase):
    def run_bash(
        self,
        shell_config: Path,
        command: str,
        *,
        env: dict[str, str] | None = None,
    ):
        script = f"source {shlex.quote(str(shell_config))}\n{command}"
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-c", script],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_proxy_sets_http_socks_and_node_environment(self):
        result = self.run_bash(
            SHELL_CONFIG,
            """
curl() { printf '{"ip":"203.0.113.1"}\\n'; }
proxy 10808 proxy.example >/dev/null
printf '%s\n' \
    "$http_proxy" "$https_proxy" "$socks_proxy" "$socks5_proxy" "$all_proxy" \
    "$HTTP_PROXY" "$HTTPS_PROXY" "$SOCKS_PROXY" "$SOCKS5_PROXY" "$ALL_PROXY" \
    "$no_proxy" "$NO_PROXY" "$NODE_USE_ENV_PROXY"
""",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [
                "http://proxy.example:10808",
                "http://proxy.example:10808",
                "socks5://proxy.example:10808",
                "socks5://proxy.example:10808",
                "http://proxy.example:10808",
                "http://proxy.example:10808",
                "http://proxy.example:10808",
                "socks5://proxy.example:10808",
                "socks5://proxy.example:10808",
                "http://proxy.example:10808",
                "localhost,127.0.0.1,::1",
                "localhost,127.0.0.1,::1",
                "1",
            ],
            result.stdout.splitlines(),
        )

    def test_proxy_checks_public_ip_after_setting_environment(self):
        result = self.run_bash(
            SHELL_CONFIG,
            """
curl() { printf 'curl %s\n' "$*"; }
proxy 10808
""",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            "curl --fail --silent --show-error https://api.ipify.org?format=json",
            result.stdout,
        )

    def test_proxy_rejects_invalid_port(self):
        result = self.run_bash(SHELL_CONFIG, "proxy 65536")

        self.assertEqual(2, result.returncode)
        self.assertIn("端口无效", result.stderr)

    def test_proxy_requires_port(self):
        result = self.run_bash(SHELL_CONFIG, "proxy")

        self.assertEqual(2, result.returncode)
        self.assertIn("proxy <端口>", result.stderr)

    def test_unproxy_clears_all_managed_environment(self):
        result = self.run_bash(
            SHELL_CONFIG,
            """
curl() { printf '{"ip":"203.0.113.1"}\\n'; }
proxy 10808 proxy.example >/dev/null
unproxy >/dev/null
for name in \
    http_proxy https_proxy socks_proxy socks5_proxy all_proxy \
    HTTP_PROXY HTTPS_PROXY SOCKS_PROXY SOCKS5_PROXY ALL_PROXY \
    no_proxy NO_PROXY NODE_USE_ENV_PROXY; do
    if [[ -v "$name" ]]; then
        printf 'still set: %s\n' "$name" >&2
        exit 1
    fi
done
""",
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_codex_p_selects_provider_and_forwards_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            bin_dir = temporary / "bin"
            bin_dir.mkdir()
            fake_codex = bin_dir / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\"\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

            result = self.run_bash(SHELL_CONFIG, "codex-p example --version", env=env)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                ["-c", 'model_provider="example"', "--version"],
                result.stdout.splitlines(),
            )

    def test_codex_p_rejects_unsafe_provider(self):
        result = self.run_bash(SHELL_CONFIG, "codex-p '../unsafe'")

        self.assertEqual(2, result.returncode)
        self.assertIn("invalid provider", result.stderr)

    def test_add_copies_current_codex_and_delete_removes_profile_and_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            home = temporary / "home"
            source_home = home / ".codex"
            source_home.mkdir(parents=True)
            (source_home / "config.toml").write_text("model = 'test'\n", encoding="utf-8")
            shell_config = home / ".bash_aliases"
            shell_config.write_bytes(SHELL_CONFIG.read_bytes())

            env = os.environ.copy()
            env["HOME"] = str(home)

            added = self.run_bash(
                shell_config,
                "codex-env-add work\nalias codex-work",
                env=env,
            )

            profile_home = home / ".codex-env" / ".codex-work"
            alias_line = (
                "alias codex-work='CODEX_HOME=\"$HOME/.codex-env/.codex-work\" codex --disable apps'"
            )
            self.assertEqual(0, added.returncode, added.stderr)
            self.assertEqual("model = 'test'\n", (profile_home / "config.toml").read_text())
            self.assertIn(alias_line, shell_config.read_text(encoding="utf-8"))
            self.assertIn(alias_line, added.stdout)

            deleted = self.run_bash(shell_config, "codex-env-delete work", env=env)

            self.assertEqual(0, deleted.returncode, deleted.stderr)
            self.assertFalse(profile_home.exists())
            self.assertNotIn(alias_line, shell_config.read_text(encoding="utf-8"))

    def test_add_excludes_runtime_auth_history_and_memory_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            source_home = home / ".codex"
            source_home.mkdir(parents=True)
            retained = [
                "config.toml", "AGENTS.md", ".sandbox_migration", ".custom-settings",
                "skills/example/SKILL.md", "rules/default.rules",
                "plugins/cache/plugin.txt", "packages/app-server-daemon/binary",
                "database-schema-bootstrap/state/state_1.sqlite",
                "custom/cache/keep.txt", "app-settings/keep.txt",
            ]
            excluded = [
                "app-server-control/app-server-startup.lock",
                "app-server-daemon/daemon.pid", "cache/cached.json", "tmp/arg0/file",
                ".tmp/file", "log/codex.log", "models_cache.json",
                "shell_snapshots/snapshot.sh", "tui-thread-reference-capabilities/file",
                "thread-writer-locks/thread.lock", "mcp-oauth-locks/oauth.lock",
                ".sqlite-maintenance.lock", "session_index.jsonl.lock",
                "auth.json", "auth.json.bak", ".credentials.json", ".credentials.json.bak",
                "sessions/2026/rollout.jsonl", "archived_sessions/rollout.jsonl",
                "history.jsonl", "session_index.jsonl", "generated_images/image.png",
                "memories/summary.md",
            ]
            for database in (
                "state_5", "thread_history_1", "logs_2", "memories_1",
                "memories_v2_1", "goals_1", "queue_1",
            ):
                excluded.extend(f"{database}.sqlite{suffix}" for suffix in ("", "-wal", "-shm"))
            for relative in retained + excluded:
                path = source_home / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative, encoding="utf-8")
            (source_home / "skills-link").symlink_to("skills", target_is_directory=True)
            shell_config = home / ".bash_aliases"
            shell_config.write_bytes(SHELL_CONFIG.read_bytes())
            env = os.environ.copy()
            env["HOME"] = str(home)

            # 排除真实 Unix Socket，验证过滤发生在复制之前。
            socket_path = source_home / "app-server-control.sock"
            with socket.socket(socket.AF_UNIX) as control_socket:
                control_socket.bind(str(socket_path))
                added = self.run_bash(
                    shell_config,
                    'before=$(shopt -p dotglob nullglob failglob)\n'
                    'codex-env-add work || exit $?\n'
                    '[[ "$before" == "$(shopt -p dotglob nullglob failglob)" ]]',
                    env=env,
                )
            self.assertEqual(0, added.returncode, added.stderr)
            profile_home = home / ".codex-env" / ".codex-work"
            self.assertEqual(0o700, profile_home.stat().st_mode & 0o777)
            for relative in retained:
                with self.subTest(retained=relative):
                    self.assertEqual(relative, (profile_home / relative).read_text())
            for relative in excluded:
                with self.subTest(excluded=relative):
                    self.assertFalse((profile_home / relative).exists())
                    self.assertEqual(relative, (source_home / relative).read_text())
            self.assertTrue(socket_path.is_socket())
            self.assertFalse((profile_home / socket_path.name).exists())
            self.assertEqual("skills", os.readlink(profile_home / "skills-link"))

    def test_add_removes_partial_profile_without_registering_alias_when_copy_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            source_home = home / ".codex"
            source_home.mkdir(parents=True)
            (source_home / "config.toml").write_text("model = 'test'\n", encoding="utf-8")
            shell_config = home / ".bash_aliases"
            original = SHELL_CONFIG.read_bytes()
            shell_config.write_bytes(original)
            env = os.environ.copy()
            env["HOME"] = str(home)

            result = self.run_bash(
                shell_config,
                'cp() { command cp "$@"; return 1; }\ncodex-env-add work',
                env=env,
            )

            self.assertEqual(1, result.returncode)
            self.assertIn("cannot copy profile", result.stderr)
            self.assertFalse((home / ".codex-env" / ".codex-work").exists())
            self.assertEqual(original, shell_config.read_bytes())
            self.assertEqual("model = 'test'\n", (source_home / "config.toml").read_text())

    def test_add_rejects_unsafe_name(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            home = temporary / "home"
            (home / ".codex").mkdir(parents=True)
            shell_config = home / ".bash_aliases"
            shell_config.write_bytes(SHELL_CONFIG.read_bytes())
            env = os.environ.copy()
            env["HOME"] = str(home)

            result = self.run_bash(shell_config, "codex-env-add ../outside", env=env)

            self.assertEqual(2, result.returncode)
            self.assertIn("invalid name", result.stderr)
            self.assertFalse((temporary / "outside").exists())

    def test_add_preserves_existing_dangling_profile_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            (home / ".codex").mkdir(parents=True)
            profiles_root = home / ".codex-env"
            profiles_root.mkdir()
            profile_home = profiles_root / ".codex-work"
            profile_home.symlink_to("missing-profile", target_is_directory=True)
            shell_config = home / ".bash_aliases"
            original = SHELL_CONFIG.read_bytes()
            shell_config.write_bytes(original)
            env = os.environ.copy()
            env["HOME"] = str(home)

            result = self.run_bash(shell_config, "codex-env-add work", env=env)

            self.assertEqual(1, result.returncode)
            self.assertIn("profile already exists", result.stderr)
            self.assertTrue(profile_home.is_symlink())
            self.assertEqual("missing-profile", os.readlink(profile_home))
            self.assertEqual(original, shell_config.read_bytes())

    def test_delete_handles_legacy_and_custom_aliases_without_removing_other_entries(self):
        for command in ("codex", "codex --disable apps --model test"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                home = Path(directory) / "home"
                profile_home = home / ".codex-env" / ".codex-work"
                profile_home.mkdir(parents=True)
                shell_config = home / ".bash_aliases"
                target = f"alias codex-work='CODEX_HOME=\"$HOME/.codex-env/.codex-work\" {command}'\n"
                other = "alias codex-work-extra='codex --version'\n"
                outside = "alias codex-work='codex --help'\n"
                start = "# >>> dev-env:codex-env aliases >>>\n"
                original = SHELL_CONFIG.read_text(encoding="utf-8")
                shell_config.write_text(
                    outside + original.replace(start, start + target + other),
                    encoding="utf-8",
                )
                env = os.environ.copy()
                env["HOME"] = str(home)

                result = self.run_bash(shell_config, "codex-env-delete work", env=env)

                self.assertEqual(0, result.returncode, result.stderr)
                self.assertFalse(profile_home.exists())
                self.assertEqual(
                    outside + original.replace(start, start + other),
                    shell_config.read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
