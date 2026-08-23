from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable


class AdapterError(RuntimeError):
    pass


class AdapterRegistry:
    def __init__(self, adapters: Iterable[object]) -> None:
        self._adapters = {}
        for adapter in adapters:
            name = str(adapter.name)
            if name in self._adapters:
                raise AdapterError(f"duplicate adapter: {name}")
            self._adapters[name] = adapter

    def ordered(self, names: Iterable[str] = ()) -> list[object]:
        requested = tuple(names)
        selected = set(requested) if requested else set(self._adapters)
        unknown = selected - set(self._adapters)
        if unknown:
            raise AdapterError(f"unknown adapter: {', '.join(sorted(unknown))}")

        ordered: list[object] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visited or name not in selected:
                return
            if name in visiting:
                raise AdapterError("dependency cycle detected")
            visiting.add(name)
            adapter = self._adapters[name]
            for dependency in adapter.depends_on:
                if dependency not in self._adapters:
                    raise AdapterError(f"adapter {name} depends on missing adapter: {dependency}")
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
            ordered.append(adapter)

        for name in sorted(selected):
            visit(name)
        return ordered


def discover_adapters() -> AdapterRegistry:
    adapters = []
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_") or module_info.name == "base":
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        adapter = getattr(module, "ADAPTER", None)
        if adapter is not None:
            adapters.append(adapter)
    return AdapterRegistry(adapters)
