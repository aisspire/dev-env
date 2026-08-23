import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_env.cli import run


class FakeTransaction:
    def __init__(self, *, scopes=("mise",), changes=(), changed=True):
        self.scopes = tuple(scopes)
        self.changes = tuple(changes)
        self.changed = changed
        self.entered = False
        self.retained = False
        self.rolled_back = False

    def __enter__(self):
        self.entered = True
        return self

    def retain(self):
        self.retained = True

    def __exit__(self, exc_type, exc_value, traceback):
        self.rolled_back = not self.retained
        return False


class FakeService:
    def __init__(self, *, converged=False, actions=None):
        self.document = {
            "schema_version": 1,
            "platform": {"os": "ubuntu"},
            "adapters": {},
            "summary": {"converged": converged, "missing": 0, "extra": 0, "findings": 0},
        }
        self.plan_document = {
            "schema_version": 1,
            "actions": list(actions or []),
            "summary": {"total": len(actions or [])},
        }
        self.applied = []
        self.inventory_path = None
        self.inventory_document = None
        self.inventory_calls = 0
        self.fail_plan = False
        self.fail_apply = False
        self.add_transaction = FakeTransaction()

    def inventory(self):
        self.inventory_calls += 1
        return self.document

    def plan(self, scopes=()):
        if self.fail_plan:
            raise RuntimeError("plan failed")
        self.last_plan_scopes = list(scopes)
        return self.plan_document

    def apply(self, scopes=(), confirmed=False):
        self.applied.append((tuple(scopes), confirmed))
        if self.fail_apply:
            raise RuntimeError("apply failed")
        return self.document

    def prepare_add(self, raw_specs):
        self.added_specs = list(raw_specs)
        return self.add_transaction

    def write_inventory(self, path=None, *, document=None):
        self.inventory_path = path
        self.inventory_document = document
        return path or Path("inventory/current.json")


class CliTests(unittest.TestCase):
    def test_status_json_writes_only_machine_document(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        service = FakeService(converged=True)

        exit_code = run(["status", "--json"], service, stdout=stdout, stderr=stderr)

        self.assertEqual(0, exit_code)
        self.assertEqual(service.document, json.loads(stdout.getvalue()))
        self.assertEqual("", stderr.getvalue())

    def test_check_returns_two_when_drift_exists(self):
        stdout = io.StringIO()

        exit_code = run(["check", "--json"], FakeService(converged=False), stdout=stdout, stderr=io.StringIO())

        self.assertEqual(2, exit_code)

    def test_plan_returns_two_and_filters_scope(self):
        stdout = io.StringIO()
        service = FakeService(actions=[{"adapter": "apt", "action": "create"}])

        exit_code = run(["plan", "--json", "--scope", "apt"], service, stdout=stdout, stderr=io.StringIO())

        self.assertEqual(2, exit_code)
        self.assertEqual(["apt"], service.last_plan_scopes)

    def test_plan_accepts_scope_from_a_future_dynamic_adapter(self):
        service = FakeService(converged=True)

        exit_code = run(
            ["plan", "--scope", "docker"],
            service,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(["docker"], service.last_plan_scopes)

    def test_apply_prompts_once_and_refreshes_inventory(self):
        stdout = io.StringIO()
        prompts = []
        service = FakeService(actions=[{"adapter": "mise", "action": "create", "name": "java"}])

        exit_code = run(
            ["apply", "--scope", "mise"],
            service,
            stdout=stdout,
            stderr=io.StringIO(),
            input_fn=lambda prompt: prompts.append(prompt) or "y",
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(prompts))
        self.assertEqual([(("mise",), True)], service.applied)
        self.assertEqual(ROOT / "inventory" / "current.json", service.inventory_path)
        self.assertIs(service.document, service.inventory_document)

    def test_apply_without_actions_does_not_prompt(self):
        prompts = []
        service = FakeService(converged=True)

        exit_code = run(
            ["apply"],
            service,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            input_fn=lambda prompt: prompts.append(prompt) or "n",
        )

        self.assertEqual(0, exit_code)
        self.assertEqual([], prompts)
        self.assertEqual([], service.applied)

    def test_inventory_uses_atomic_service_writer(self):
        service = FakeService(converged=True)

        exit_code = run(["inventory"], service, stdout=io.StringIO(), stderr=io.StringIO())

        self.assertEqual(0, exit_code)
        self.assertEqual(ROOT / "inventory" / "current.json", service.inventory_path)

    def test_add_prompts_once_applies_derived_scopes_and_refreshes_inventory(self):
        stdout = io.StringIO()
        prompts = []
        service = FakeService(
            actions=[{"adapter": "mise", "kind": "tool", "action": "create", "name": "node@26"}]
        )
        service.add_transaction = FakeTransaction(
            scopes=("apt", "mise"),
            changes=(
                SimpleNamespace(adapter="apt", key="apt:jq", version="latest", action="add"),
                SimpleNamespace(adapter="mise", key="node", version="26", action="append"),
            ),
        )

        exit_code = run(
            ["add", "apt:jq", "node@26"],
            service,
            stdout=stdout,
            stderr=io.StringIO(),
            input_fn=lambda prompt: prompts.append(prompt) or "y",
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(["apt:jq", "node@26"], service.added_specs)
        self.assertEqual(["apt", "mise"], service.last_plan_scopes)
        self.assertEqual([(("apt", "mise"), True)], service.applied)
        self.assertEqual(1, len(prompts))
        self.assertTrue(service.add_transaction.retained)
        self.assertFalse(service.add_transaction.rolled_back)
        self.assertIs(service.document, service.inventory_document)
        self.assertIn("add apt:declaration apt:jq@latest", stdout.getvalue())
        self.assertIn("append mise:declaration node@26", stdout.getvalue())

    def test_add_cancel_rolls_back_staged_config(self):
        stderr = io.StringIO()
        service = FakeService(
            actions=[{"adapter": "apt", "kind": "package", "action": "create", "name": "apt:jq"}]
        )
        service.add_transaction = FakeTransaction(
            scopes=("apt",),
            changes=(SimpleNamespace(adapter="apt", key="apt:jq", version="latest", action="add"),),
        )

        exit_code = run(
            ["add", "apt:jq"],
            service,
            stdout=io.StringIO(),
            stderr=stderr,
            input_fn=lambda _: "n",
        )

        self.assertEqual(1, exit_code)
        self.assertTrue(service.add_transaction.rolled_back)
        self.assertFalse(service.add_transaction.retained)
        self.assertEqual([], service.applied)
        self.assertIn("add cancelled", stderr.getvalue())

    def test_add_yes_runs_mise_apply_to_refresh_lock_even_without_plan_actions(self):
        prompts = []
        service = FakeService(converged=True)
        service.add_transaction = FakeTransaction(
            scopes=("mise",),
            changes=(
                SimpleNamespace(
                    adapter="mise",
                    key="aqua:openai/codex",
                    version="latest",
                    action="add",
                ),
            ),
        )

        exit_code = run(
            ["add", "--yes", "aqua:openai/codex@latest"],
            service,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            input_fn=lambda prompt: prompts.append(prompt) or "n",
        )

        self.assertEqual(0, exit_code)
        self.assertEqual([], prompts)
        self.assertEqual([(("mise",), True)], service.applied)
        self.assertTrue(service.add_transaction.retained)

    def test_add_plan_failure_rolls_back_but_apply_failure_keeps_declaration(self):
        plan_service = FakeService()
        plan_service.fail_plan = True

        plan_result = run(
            ["add", "node@26"],
            plan_service,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        self.assertEqual(1, plan_result)
        self.assertTrue(plan_service.add_transaction.rolled_back)

        apply_service = FakeService(
            actions=[{"adapter": "mise", "kind": "tool", "action": "create", "name": "node@26"}]
        )
        apply_service.fail_apply = True
        stderr = io.StringIO()

        apply_result = run(
            ["add", "--yes", "node@26"],
            apply_service,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(1, apply_result)
        self.assertTrue(apply_service.add_transaction.retained)
        self.assertFalse(apply_service.add_transaction.rolled_back)
        self.assertEqual(ROOT / "inventory" / "current.json", apply_service.inventory_path)
        self.assertIn("apply failed", stderr.getvalue())

    def test_add_interrupt_during_apply_keeps_declaration_and_refreshes_inventory(self):
        service = FakeService(
            actions=[{"adapter": "mise", "kind": "tool", "action": "create", "name": "node@26"}]
        )

        def interrupt(*args, **kwargs):
            service.applied.append((tuple(args[0]), kwargs["confirmed"]))
            raise KeyboardInterrupt

        service.apply = interrupt

        with self.assertRaises(KeyboardInterrupt):
            run(
                ["add", "--yes", "node@26"],
                service,
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

        self.assertTrue(service.add_transaction.retained)
        self.assertFalse(service.add_transaction.rolled_back)
        self.assertEqual(ROOT / "inventory" / "current.json", service.inventory_path)


if __name__ == "__main__":
    unittest.main()
