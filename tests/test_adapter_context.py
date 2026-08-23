import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.adapters.base import AdapterContext


class CountingBackend:
    def __init__(self):
        self.runner = object()
        self.calls = []

    def status(self):
        self.calls.append("status")
        return {"packages": {}}

    def plan(self):
        self.calls.append("plan")
        return {"resources": []}

    def installed_tools(self):
        self.calls.append("installed_tools")
        return {}


class RustupBackend:
    pass


class AdapterContextTests(unittest.TestCase):
    def test_exposes_shared_runner_and_repository_root(self):
        backend = CountingBackend()
        rustup = RustupBackend()
        context = AdapterContext(ROOT, backend, rustup)

        self.assertIs(backend.runner, context.runner)
        self.assertIs(rustup, context.rustup)
        self.assertEqual(ROOT, context.repo_root)

    def test_lazily_caches_native_observations_for_all_adapters(self):
        backend = CountingBackend()
        context = AdapterContext(ROOT, backend, RustupBackend())

        self.assertIs(context.bootstrap_status, context.bootstrap_status)
        self.assertIs(context.bootstrap_plan, context.bootstrap_plan)
        self.assertIs(context.installed_tools, context.installed_tools)

        self.assertEqual(["status", "plan", "installed_tools"], backend.calls)


if __name__ == "__main__":
    unittest.main()
