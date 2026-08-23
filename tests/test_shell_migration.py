import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.adapters.mise import deduplicate_legacy_activation, repair_legacy_bashrc


MANAGED_BLOCK = """# >>> mise:activate >>> managed by mise - do not edit between markers
eval "$(mise activate bash)"
# <<< mise:activate <<<
"""


class ShellMigrationTests(unittest.TestCase):
    def test_leaves_legacy_line_until_mise_has_created_managed_block(self):
        original = 'export EDITOR=vim\neval "$(mise activate bash)"\n'

        self.assertEqual(original, deduplicate_legacy_activation(original))

    def test_removes_only_duplicate_legacy_lines_outside_managed_block(self):
        original = (
            'export EDITOR=vim\n'
            'eval "$(mise activate bash)"\n'
            + MANAGED_BLOCK
            + 'alias m="mise"\n'
            + '  eval "$(mise activate bash)"  \n'
        )

        migrated = deduplicate_legacy_activation(original)

        self.assertEqual(1, migrated.count('eval "$(mise activate bash)"'))
        self.assertIn(MANAGED_BLOCK, migrated)
        self.assertIn('export EDITOR=vim\n', migrated)
        self.assertIn('alias m="mise"\n', migrated)

    def test_repairs_file_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            bashrc = Path(directory) / ".bashrc"
            bashrc.write_text('eval "$(mise activate bash)"\n' + MANAGED_BLOCK, encoding="utf-8")

            self.assertTrue(repair_legacy_bashrc(bashrc))
            first = bashrc.read_bytes()
            self.assertFalse(repair_legacy_bashrc(bashrc))
            self.assertEqual(first, bashrc.read_bytes())


if __name__ == "__main__":
    unittest.main()
