from __future__ import annotations

import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Sequence, TextIO

from .backend import MiseBackend, RustupBackend
from .cli import REPO_ROOT, run, write_error, write_manual_hint
from .runner import CommandRunner
from .service import EnvironmentService


def build_service(
    repo_root: Path,
    *,
    mise_binary: str,
    rustup_binary: str | None = None,
) -> EnvironmentService:
    runner = CommandRunner()
    backend = MiseBackend(repo_root, runner, mise_binary=mise_binary)
    rustup_backend = RustupBackend(repo_root, runner, rustup_binary=rustup_binary)
    return EnvironmentService(repo_root, backend, rustup_backend=rustup_backend)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or "-h" in arguments or "--help" in arguments:
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                run(arguments, None, stdout=stdout, stderr=stderr)
        except SystemExit as error:
            exit_code = int(error.code or 0)
            if exit_code:
                write_manual_hint(stderr)
            return exit_code

    mise_binary = shutil.which("mise")
    if mise_binary is None:
        write_error("error: mise is not installed; run ./scripts/bootstrap first", stderr)
        return 1
    service = build_service(
        REPO_ROOT,
        mise_binary=mise_binary,
        rustup_binary=shutil.which("rustup"),
    )
    return run(
        arguments,
        service,
        stdout=stdout,
        stderr=stderr,
    )
