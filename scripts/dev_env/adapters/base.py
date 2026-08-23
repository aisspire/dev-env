from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Any, Protocol


class AdapterContext:
    """Shared, lazy operation context available to every adapter."""

    def __init__(
        self,
        repo_root: Path,
        mise_backend: Any,
        rustup_backend: Any | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.mise = mise_backend
        self.rustup = rustup_backend
        self.runner = mise_backend.runner

    @cached_property
    def bootstrap_status(self) -> dict[str, Any]:
        return self.mise.status()

    @cached_property
    def bootstrap_plan(self) -> dict[str, Any]:
        return self.mise.plan()

    @cached_property
    def installed_tools(self) -> dict[str, Any]:
        return self.mise.installed_tools()


class Adapter(Protocol):
    name: str
    depends_on: tuple[str, ...]

    def probe(self, context: AdapterContext) -> dict[str, Any]: ...

    def plan(self, context: AdapterContext) -> list[dict[str, Any]]: ...

    def apply(self, context: AdapterContext, *, confirmed: bool) -> None: ...
