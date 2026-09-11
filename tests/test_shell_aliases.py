import os
import shlex
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
                "alias codex-work='CODEX_HOME=\"$HOME/.codex-env/.codex-work\" codex'"
            )
            self.assertEqual(0, added.returncode, added.stderr)
            self.assertEqual("model = 'test'\n", (profile_home / "config.toml").read_text())
            self.assertIn(alias_line, shell_config.read_text(encoding="utf-8"))
            self.assertIn(alias_line, added.stdout)

            deleted = self.run_bash(shell_config, "codex-env-delete work", env=env)

            self.assertEqual(0, deleted.returncode, deleted.stderr)
            self.assertFalse(profile_home.exists())
            self.assertNotIn(alias_line, shell_config.read_text(encoding="utf-8"))

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


if __name__ == "__main__":
    unittest.main()
