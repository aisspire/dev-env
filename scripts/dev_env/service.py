from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Callable, Iterable

from .adapters import AdapterRegistry, discover_adapters
from .adapters.base import AdapterContext
from .declarations import prepare_add_transaction
from .normalize import SCHEMA_VERSION
from .platform_info import collect_platform


def write_json_atomic(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(document, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


class EnvironmentService:
    def __init__(
        self,
        repo_root: Path,
        backend,
        *,
        rustup_backend=None,
        adapters: AdapterRegistry | None = None,
        platform_probe: Callable[[], dict] = collect_platform,
    ) -> None:
        self.repo_root = repo_root
        self.backend = backend
        self.rustup_backend = rustup_backend
        self.adapters = adapters or discover_adapters()
        self.platform_probe = platform_probe

    def _context(self) -> AdapterContext:
        return AdapterContext(self.repo_root, self.backend, self.rustup_backend)

    def prepare_add(self, raw_specs: Iterable[str]):
        return prepare_add_transaction(self.repo_root / "mise.toml", raw_specs)

    def inventory(self) -> dict:
        context = self._context()
        adapter_states = {
            adapter.name: adapter.probe(context)
            for adapter in self.adapters.ordered()
        }
        missing = sum(len(state.get("missing", [])) for state in adapter_states.values())
        extra = sum(len(state.get("extra", [])) for state in adapter_states.values())
        findings = sum(len(state.get("findings", [])) for state in adapter_states.values())
        converged = all(state.get("status") == "converged" for state in adapter_states.values())
        return {
            "schema_version": SCHEMA_VERSION,
            "platform": self.platform_probe(),
            "adapters": adapter_states,
            "summary": {
                "converged": converged,
                "missing": missing,
                "extra": extra,
                "findings": findings,
            },
        }

    def plan(self, scopes: Iterable[str] = ()) -> dict:
        context = self._context()
        actions = []
        for adapter in self.adapters.ordered(scopes):
            actions.extend(adapter.plan(context))
        actions.sort(key=lambda item: (item["adapter"], item["kind"], item["name"]))
        return {
            "schema_version": SCHEMA_VERSION,
            "actions": actions,
            "summary": {
                "create": sum(1 for item in actions if item["action"] == "create"),
                "repair": sum(1 for item in actions if item["action"] == "repair"),
                "total": len(actions),
            },
        }

    def apply(self, scopes: Iterable[str] = (), *, confirmed: bool) -> dict:
        context = self._context()
        for adapter in self.adapters.ordered(scopes):
            adapter.apply(context, confirmed=confirmed)
        return self.inventory()

    def write_inventory(self, path: Path | None = None, *, document: dict | None = None) -> Path:
        target = path or self.repo_root / "inventory" / "current.json"
        write_json_atomic(target, document if document is not None else self.inventory())
        return target
