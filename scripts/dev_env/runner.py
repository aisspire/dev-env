from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass
class CommandError(RuntimeError):
    command: tuple[str, ...]
    returncode: int
    stderr: str

    def __str__(self) -> str:
        rendered = " ".join(self.command)
        detail = self.stderr.strip() or "command failed"
        return f"{rendered} exited with {self.returncode}: {detail}"


class CommandRunner:
    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise CommandError(tuple(command), completed.returncode, completed.stderr)
        return completed

    def run_interactive(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            shell=False,
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            raise CommandError(tuple(command), completed.returncode, "interactive command failed")
        return completed

    def run_json(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Any:
        completed = self.run(command, cwd=cwd, env=env)
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise CommandError(tuple(command), completed.returncode, f"invalid JSON: {error}") from error
