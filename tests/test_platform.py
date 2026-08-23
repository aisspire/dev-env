import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.platform_info import parse_platform


class PlatformTests(unittest.TestCase):
    def test_parses_stable_wsl_platform_fields(self):
        os_release = 'NAME="Ubuntu"\nID=ubuntu\nVERSION_ID="26.04"\n'

        result = parse_platform(os_release, "Linux version microsoft-standard-WSL2", "systemd", "x86_64")

        self.assertEqual(
            {
                "os": "ubuntu",
                "version": "26.04",
                "architecture": "x86_64",
                "wsl": True,
                "init": "systemd",
            },
            result,
        )


if __name__ == "__main__":
    unittest.main()
