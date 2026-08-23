import sys
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.rustup_config import RustupConfigError, load_rustup_config, parse_rustup_config


class RepositoryRustupConfigTests(unittest.TestCase):
    def test_declares_stable_and_nightly_with_minimal_profile(self):
        config = load_rustup_config(ROOT / "rustup.toml")

        self.assertEqual(1, config.schema_version)
        self.assertEqual("stable", config.default_toolchain)
        self.assertEqual("minimal", config.profile)
        self.assertEqual(["stable", "nightly"], [item.name for item in config.toolchains])
        for toolchain in config.toolchains:
            self.assertEqual(("clippy", "rust-analyzer", "rustfmt"), toolchain.components)
            self.assertEqual((), toolchain.targets)

    def test_root_file_has_only_the_documented_schema(self):
        with (ROOT / "rustup.toml").open("rb") as config_file:
            document = tomllib.load(config_file)

        self.assertEqual(
            {"schema_version", "default_toolchain", "profile", "toolchains"},
            set(document),
        )


class RustupConfigValidationTests(unittest.TestCase):
    def valid_document(self):
        return {
            "schema_version": 1,
            "default_toolchain": "stable",
            "profile": "minimal",
            "toolchains": {
                "stable": {
                    "components": ["clippy", "rust-analyzer", "rustfmt"],
                    "targets": [],
                },
                "nightly": {
                    "components": ["clippy", "rust-analyzer", "rustfmt"],
                    "targets": [],
                },
            },
        }

    def test_accepts_official_version_date_and_cross_target_names(self):
        document = self.valid_document()
        document["default_toolchain"] = "1.92.0"
        document["toolchains"] = {
            "1.92.0": {
                "components": ["llvm-tools-preview"],
                "targets": ["wasm32-unknown-unknown"],
            },
            "nightly-2026-08-20": {
                "components": ["rustc-dev"],
                "targets": ["aarch64-unknown-linux-gnu"],
            },
        }

        config = parse_rustup_config(document)

        self.assertEqual("1.92.0", config.default_toolchain)
        self.assertEqual(
            ["1.92.0", "nightly-2026-08-20"],
            [item.name for item in config.toolchains],
        )

    def test_rejects_schema_profile_and_undeclared_default_errors(self):
        cases = []

        wrong_schema = self.valid_document()
        wrong_schema["schema_version"] = 2
        cases.append((wrong_schema, "schema_version"))

        wrong_profile = self.valid_document()
        wrong_profile["profile"] = "custom"
        cases.append((wrong_profile, "profile"))

        missing_default = self.valid_document()
        missing_default["default_toolchain"] = "beta"
        cases.append((missing_default, "not declared"))

        for document, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(RustupConfigError, message):
                parse_rustup_config(document)

    def test_rejects_duplicate_component_and_target_entries(self):
        duplicate_component = self.valid_document()
        duplicate_component["toolchains"]["stable"]["components"] = ["clippy", "clippy"]

        duplicate_target = self.valid_document()
        duplicate_target["toolchains"]["nightly"]["targets"] = [
            "wasm32-unknown-unknown",
            "wasm32-unknown-unknown",
        ]

        for document in (duplicate_component, duplicate_target):
            with self.subTest(document=document), self.assertRaisesRegex(
                RustupConfigError,
                "duplicate value",
            ):
                parse_rustup_config(document)

    def test_rejects_unsafe_names_and_unknown_keys(self):
        unsafe_toolchain = self.valid_document()
        unsafe_toolchain["default_toolchain"] = "--help"

        unsafe_component = self.valid_document()
        unsafe_component["toolchains"]["stable"]["components"] = ["../../rustfmt"]

        unsafe_target = self.valid_document()
        unsafe_target["toolchains"]["stable"]["targets"] = ["--target"]

        unknown_key = self.valid_document()
        unknown_key["download_root"] = "https://example.invalid"

        for document, message in (
            (unsafe_toolchain, "safe official"),
            (unsafe_component, "safe name"),
            (unsafe_target, "safe name"),
            (unknown_key, "unknown key"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(RustupConfigError, message):
                parse_rustup_config(document)

    def test_rejects_invalid_calendar_date(self):
        document = self.valid_document()
        document["default_toolchain"] = "nightly-2026-02-30"
        document["toolchains"] = {
            "nightly-2026-02-30": {"components": [], "targets": []},
        }

        with self.assertRaisesRegex(RustupConfigError, "invalid date"):
            parse_rustup_config(document)


if __name__ == "__main__":
    unittest.main()
