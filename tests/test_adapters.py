import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.adapters import AdapterError, AdapterRegistry, discover_adapters
from dev_env.adapters.mise import MiseAdapter
from dev_env.adapters.rustup import RustupAdapter


class StubAdapter:
    def __init__(self, name, depends_on=()):
        self.name = name
        self.depends_on = tuple(depends_on)


class AdapterRegistryTests(unittest.TestCase):
    def test_orders_dependencies_before_consumers(self):
        registry = AdapterRegistry([StubAdapter("mise", ("apt",)), StubAdapter("apt")])

        self.assertEqual(["apt", "mise"], [adapter.name for adapter in registry.ordered()])

    def test_scope_accepts_any_iterable_without_consuming_it_twice(self):
        registry = AdapterRegistry([StubAdapter("mise", ("apt",)), StubAdapter("apt")])

        selected = registry.ordered(name for name in ["mise"])

        self.assertEqual(["mise"], [adapter.name for adapter in selected])

    def test_rejects_duplicate_names(self):
        with self.assertRaisesRegex(AdapterError, "duplicate adapter: apt"):
            AdapterRegistry([StubAdapter("apt"), StubAdapter("apt")])

    def test_rejects_unknown_scope_after_cli_parsing(self):
        registry = AdapterRegistry([StubAdapter("apt")])

        with self.assertRaisesRegex(AdapterError, "unknown adapter: docker"):
            registry.ordered(("docker",))

    def test_rejects_dependency_cycles(self):
        registry = AdapterRegistry([StubAdapter("apt", ("mise",)), StubAdapter("mise", ("apt",))])

        with self.assertRaisesRegex(AdapterError, "dependency cycle"):
            registry.ordered()

    def test_discovers_builtin_adapters_without_core_registration(self):
        registry = discover_adapters()

        self.assertEqual(["apt", "mise", "rustup"], [adapter.name for adapter in registry.ordered()])

    def test_mise_apply_repairs_legacy_shell_activation_after_native_apply(self):
        backend = Mock()
        context = Mock()
        context.mise = backend
        adapter = MiseAdapter()

        with patch("dev_env.adapters.mise.repair_legacy_bashrc") as repair:
            adapter.apply(context, confirmed=True)

        backend.apply.assert_called_once_with(("mise",), confirmed=True)
        repair.assert_called_once()

    def test_rustup_adapter_delegates_to_dedicated_backend(self):
        context = Mock()
        adapter = RustupAdapter()

        adapter.apply(context, confirmed=True)

        context.rustup.apply.assert_called_once_with(confirmed=True)


if __name__ == "__main__":
    unittest.main()
