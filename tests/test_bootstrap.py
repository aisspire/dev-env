import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts" / "bootstrap"


class BootstrapTests(unittest.TestCase):
    def run_with_os_release(self, content: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            os_release = Path(directory) / "os-release"
            os_release.write_text(content, encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = "/dev/null"
            env["DEV_ENV_OS_RELEASE_FILE"] = str(os_release)
            return subprocess.run(
                ["/bin/bash", str(BOOTSTRAP), "--dry-run", *arguments],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

    def dry_run(self, version: str, *, distro: str = "ubuntu") -> subprocess.CompletedProcess[str]:
        return self.run_with_os_release(f'ID="{distro}"\nVERSION_ID="{version}"\n')

    def test_help_explains_every_option_and_points_to_manual(self):
        result = subprocess.run(
            ["/bin/bash", str(BOOTSTRAP), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("只显示将执行的命令", result.stdout)
        self.assertIn("--scope ADAPTER", result.stdout)
        self.assertIn("apt、mise、rustup", result.stdout)
        self.assertIn("示例:", result.stdout)
        self.assertIn("完整操作手册: docs/operations.md", result.stdout)

    def test_ubuntu_26_uses_official_ppa(self):
        result = self.dry_run("26.04")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("add-apt-repository -y ppa:jdxcode/mise", result.stdout)
        self.assertIn("apt install -y mise", result.stdout)
        self.assertIn("dev-env apply", result.stdout)
        self.assertEqual("详细操作见: docs/operations.md", result.stdout.splitlines()[-1])

    def test_ubuntu_24_uses_extrepo(self):
        result = self.dry_run("24.04")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("apt install -y extrepo", result.stdout)
        self.assertIn("extrepo enable mise", result.stdout)

    def test_future_adapter_scope_passes_through_without_script_changes(self):
        result = self.run_with_os_release('ID=ubuntu\nVERSION_ID=26.04\n', "--scope", "docker")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--scope docker", result.stdout)

    def test_rejects_unsupported_distribution(self):
        result = self.dry_run("13", distro="debian")

        self.assertEqual(1, result.returncode)
        self.assertIn("Ubuntu 24.04", result.stderr)
        self.assertEqual("详细操作见: docs/operations.md", result.stderr.splitlines()[-1])

    def test_missing_scope_value_points_to_manual(self):
        result = self.run_with_os_release('ID=ubuntu\nVERSION_ID=26.04\n', "--scope")

        self.assertEqual(1, result.returncode)
        self.assertIn("--scope requires an adapter name", result.stderr)
        self.assertEqual("详细操作见: docs/operations.md", result.stderr.splitlines()[-1])

    def test_cancelled_install_points_to_manual(self):
        with tempfile.TemporaryDirectory() as directory:
            os_release = Path(directory) / "os-release"
            os_release.write_text('ID=ubuntu\nVERSION_ID=26.04\n', encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = "/dev/null"
            env["DEV_ENV_OS_RELEASE_FILE"] = str(os_release)
            result = subprocess.run(
                ["/bin/bash", str(BOOTSTRAP)],
                input="n\n",
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("bootstrap cancelled", result.stderr)
        self.assertEqual("详细操作见: docs/operations.md", result.stderr.splitlines()[-1])

    def test_treats_os_release_as_data_not_shell_code(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "executed"
            result = self.run_with_os_release(
                f'ID=ubuntu\nVERSION_ID=26.04\nprintf owned > "{marker}"\n'
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
