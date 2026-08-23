from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .runner import CommandRunner
from .rustup_backend import RustupBackend, RustupError


SCOPE_PARTS = {
    "apt": ("packages",),
    "mise": ("dotfiles", "mise-shell-activate", "tools"),
}


class MiseBackend:
    def __init__(
        self,
        repo_root: Path,
        runner: CommandRunner,
        *,
        mise_binary: str = "mise",
    ) -> None:
        self.repo_root = repo_root
        self.runner = runner
        self.mise_binary = mise_binary

    def _base(self) -> list[str]:
        return [self.mise_binary, "-C", str(self.repo_root)]

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        trusted = env.get("MISE_TRUSTED_CONFIG_PATHS", "")
        trusted_paths = [path for path in trusted.split(os.pathsep) if path]
        repo_root = str(self.repo_root)
        if repo_root not in trusted_paths:
            trusted_paths.append(repo_root)
        env["MISE_TRUSTED_CONFIG_PATHS"] = os.pathsep.join(trusted_paths)
        return env

    def status(self):
        return self.runner.run_json(
            [*self._base(), "bootstrap", "status", "--json"],
            cwd=self.repo_root,
            env=self._env(),
        )

    def plan(self):
        return self.runner.run_json(
            [*self._base(), "bootstrap", "plan", "--json"],
            cwd=self.repo_root,
            env=self._env(),
        )

    def installed_tools(self):
        return self.runner.run_json(
            [*self._base(), "ls", "--installed", "--json"],
            cwd=self.repo_root,
            env=self._env(),
        )

    def apply(self, scopes: Iterable[str] = (), *, confirmed: bool) -> None:
        requested = tuple(scopes) or ("apt", "mise")
        parts = sorted({part for scope in requested for part in SCOPE_PARTS[scope]})
        command = [*self._base(), "bootstrap", "--only", ",".join(parts)]
        if confirmed:
            command.append("--yes")
        self.runner.run_interactive(command, cwd=self.repo_root, env=self._env())
