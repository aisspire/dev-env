import sys
import stat
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class AddSpecParsingTests(unittest.TestCase):
    def test_parses_apt_mise_and_scoped_npm_specs(self):
        try:
            from dev_env.declarations import parse_add_spec
        except ModuleNotFoundError:
            self.fail("dev_env.declarations.parse_add_spec is not implemented")

        cases = {
            "apt:jq": ("apt", "apt:jq", "latest"),
            "node@26": ("mise", "node", "26"),
            "aqua:openai/codex@latest": ("mise", "aqua:openai/codex", "latest"),
            "npm:@openai/codex": ("mise", "npm:@openai/codex", "latest"),
            "npm:@openai/codex@0.149.0": ("mise", "npm:@openai/codex", "0.149.0"),
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                parsed = parse_add_spec(raw)
                self.assertEqual(expected, (parsed.adapter, parsed.key, parsed.version))

    def test_rejects_empty_or_unsafe_specs(self):
        from dev_env.declarations import parse_add_spec

        for raw in ("", "@latest", "apt:", "node@", " node@26", "node@26\napt:jq"):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "invalid add spec"):
                parse_add_spec(raw)


class ConfigRenderingTests(unittest.TestCase):
    CONFIG = """min_version = \"2026.8.9\"

[bootstrap.packages]
\"apt:ca-certificates\" = \"latest\"
\"apt:jq\" = \"latest\"

[tools]
node = [\"22\", \"20\"]
\"aqua:openai/codex\" = \"latest\"
"""

    def test_adds_packages_and_appends_runtime_without_changing_default(self):
        try:
            from dev_env.declarations import render_additions
        except ImportError:
            self.fail("dev_env.declarations.render_additions is not implemented")
        from dev_env.declarations import parse_add_spec

        result = render_additions(
            self.CONFIG,
            [
                parse_add_spec("apt:curl"),
                parse_add_spec("node@26"),
                parse_add_spec("npm:typescript@5"),
            ],
        )

        self.assertEqual(("apt", "mise"), result.scopes)
        self.assertEqual(
            """min_version = \"2026.8.9\"

[bootstrap.packages]
\"apt:ca-certificates\" = \"latest\"
\"apt:curl\" = \"latest\"
\"apt:jq\" = \"latest\"

[tools]
node = [\"22\", \"20\", \"26\"]
\"aqua:openai/codex\" = \"latest\"
\"npm:typescript\" = \"5\"
""",
            result.content,
        )
        self.assertEqual(
            [
                ("apt", "apt:curl", "latest", "add"),
                ("mise", "node", "26", "append"),
                ("mise", "npm:typescript", "5", "add"),
            ],
            [(item.adapter, item.key, item.version, item.action) for item in result.changes],
        )

    def test_same_declaration_is_idempotent_and_scalar_change_is_rejected(self):
        from dev_env.declarations import parse_add_spec
        try:
            from dev_env.declarations import render_additions
        except ImportError:
            self.fail("dev_env.declarations.render_additions is not implemented")

        unchanged = render_additions(
            self.CONFIG,
            [parse_add_spec("apt:jq"), parse_add_spec("node@22")],
        )

        self.assertEqual(self.CONFIG, unchanged.content)
        self.assertEqual([], list(unchanged.changes))
        with self.assertRaisesRegex(ValueError, "already declared"):
            render_additions(self.CONFIG, [parse_add_spec("aqua:openai/codex@0.150.0")])

    def test_rejects_missing_tables_and_multiline_arrays_without_rewriting(self):
        from dev_env.declarations import parse_add_spec, render_additions

        with self.assertRaisesRegex(ValueError, "required TOML table"):
            render_additions('[tools]\nnode = ["22"]\n', [parse_add_spec("apt:jq")])

        multiline = """[bootstrap.packages]
"apt:curl" = "latest"

[tools]
node = [
  "22",
]
"""
        with self.assertRaisesRegex(ValueError, "single-line array"):
            render_additions(multiline, [parse_add_spec("node@26")])

    def test_rejects_two_versions_for_a_new_scalar_in_one_request(self):
        from dev_env.declarations import parse_add_spec, render_additions

        with self.assertRaisesRegex(ValueError, "already declared"):
            render_additions(
                self.CONFIG,
                [
                    parse_add_spec("npm:typescript@5"),
                    parse_add_spec("npm:typescript@6"),
                ],
            )


class AddTransactionTests(unittest.TestCase):
    CONFIG = ConfigRenderingTests.CONFIG

    def test_rolls_back_exact_file_when_context_exits_without_retain(self):
        try:
            from dev_env.declarations import prepare_add_transaction
        except ImportError:
            self.fail("dev_env.declarations.prepare_add_transaction is not implemented")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mise.toml"
            original = self.CONFIG.encode("utf-8")
            path.write_bytes(original)
            path.chmod(0o640)
            transaction = prepare_add_transaction(path, ["apt:curl", "node@26"])

            with transaction:
                self.assertIn('"apt:curl" = "latest"', path.read_text(encoding="utf-8"))
                self.assertIn('node = ["22", "20", "26"]', path.read_text(encoding="utf-8"))

            self.assertEqual(original, path.read_bytes())
            self.assertEqual(0o640, stat.S_IMODE(path.stat().st_mode))

    def test_retain_keeps_candidate_and_duplicate_specs_create_one_change(self):
        from dev_env.declarations import prepare_add_transaction

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mise.toml"
            path.write_text(self.CONFIG, encoding="utf-8")
            transaction = prepare_add_transaction(path, ["apt:curl", "apt:curl"])

            with transaction:
                transaction.retain()

            self.assertEqual(1, path.read_text(encoding="utf-8").count('"apt:curl" = "latest"'))
            self.assertEqual(1, len(transaction.changes))
            self.assertEqual(("apt",), transaction.scopes)


if __name__ == "__main__":
    unittest.main()
