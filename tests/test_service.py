import sys
import stat
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.service import EnvironmentService
from tests.test_normalize import BOOTSTRAP_PLAN, BOOTSTRAP_STATUS, INSTALLED_TOOLS


class FakeBackend:
    def __init__(self):
        self.runner = object()
        self.applied = []

    def status(self):
        return BOOTSTRAP_STATUS

    def plan(self):
        return BOOTSTRAP_PLAN

    def installed_tools(self):
        return INSTALLED_TOOLS

    def apply(self, scopes=(), *, confirmed):
        self.applied.append((tuple(scopes), confirmed))


class FakeRustupBackend:
    def __init__(self):
        self.applied = []
        self.actions = []

    def status(self):
        return {
            "status": "converged",
            "available": True,
            "manager": {"version": "1.29.0"},
            "default_toolchain": {"desired": "stable", "observed": "stable"},
            "profile": {"desired": "minimal", "observed": "minimal"},
            "desired": [],
            "observed": [],
            "missing": [],
            "extra": [],
            "findings": [],
        }

    def plan(self):
        return list(self.actions)

    def apply(self, *, confirmed):
        self.applied.append(confirmed)


class EnvironmentServiceTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.rustup_backend = FakeRustupBackend()
        self.service = EnvironmentService(
            ROOT,
            self.backend,
            rustup_backend=self.rustup_backend,
            platform_probe=lambda: {"os": "ubuntu", "version": "26.04"},
        )

    def test_collects_inventory_from_all_discovered_adapters(self):
        result = self.service.inventory()

        self.assertEqual({"apt", "mise", "rustup"}, set(result["adapters"]))
        self.assertEqual("ubuntu", result["platform"]["os"])

    def test_filters_plan_to_requested_scope(self):
        result = self.service.plan(("apt",))

        self.assertEqual(["apt"], sorted({action["adapter"] for action in result["actions"]}))
        self.assertEqual(1, result["summary"]["total"])

    def test_filters_plan_to_rustup_scope(self):
        self.rustup_backend.actions = [
            {
                "adapter": "rustup",
                "kind": "toolchain",
                "name": "nightly",
                "action": "create",
                "current": "missing",
                "desired": "installed",
            }
        ]

        result = self.service.plan(("rustup",))

        self.assertEqual(["rustup"], [action["adapter"] for action in result["actions"]])
        self.assertEqual(1, result["summary"]["total"])

    def test_applies_adapters_in_registry_order(self):
        self.service.apply(("mise", "apt"), confirmed=True)

        self.assertEqual([(("apt",), True), (("mise",), True)], self.backend.applied)

    def test_writes_stable_inventory_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory" / "current.json"

            path.parent.mkdir(parents=True)
            path.write_text("{}\n", encoding="utf-8")
            path.chmod(0o640)

            self.service.write_inventory(path)
            first = path.read_bytes()
            self.service.write_inventory(path)
            second = path.read_bytes()

            self.assertEqual(first, second)
            self.assertTrue(first.endswith(b"\n"))
            self.assertEqual([], list(path.parent.glob("*.tmp")))
            self.assertEqual(0o640, stat.S_IMODE(path.stat().st_mode))

    def test_prepares_add_transaction_against_repository_mise_toml(self):
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            (repo_root / "mise.toml").write_text(
                '[bootstrap.packages]\n"apt:curl" = "latest"\n\n[tools]\nnode = ["22"]\n',
                encoding="utf-8",
            )
            service = EnvironmentService(
                repo_root,
                self.backend,
                rustup_backend=self.rustup_backend,
                platform_probe=lambda: {"os": "ubuntu"},
            )

            transaction = service.prepare_add(["apt:jq", "node@26"])

            self.assertEqual(("apt", "mise"), transaction.scopes)
            self.assertEqual(["apt:jq", "node"], [change.key for change in transaction.changes])


if __name__ == "__main__":
    unittest.main()
