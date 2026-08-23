from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class DeclarationError(ValueError):
    pass


@dataclass(frozen=True)
class AddSpec:
    raw: str
    adapter: str
    key: str
    version: str


@dataclass(frozen=True)
class ConfigChange:
    adapter: str
    key: str
    version: str
    action: str


@dataclass(frozen=True)
class RenderedAdditions:
    content: str
    changes: tuple[ConfigChange, ...]
    scopes: tuple[str, ...]


class AddTransaction:
    def __init__(self, path: Path, original: bytes, mode: int, rendered: RenderedAdditions) -> None:
        self.path = path
        self.original = original
        self.mode = mode
        self.rendered = rendered
        self.changes = rendered.changes
        self.scopes = rendered.scopes
        self._candidate = rendered.content.encode("utf-8")
        self._entered = False
        self._retained = False

    @property
    def changed(self) -> bool:
        return self._candidate != self.original

    def __enter__(self) -> AddTransaction:
        if self.changed:
            _write_bytes_atomic(self.path, self._candidate, self.mode)
        self._entered = True
        return self

    def retain(self) -> None:
        if not self._entered:
            raise RuntimeError("add transaction has not been entered")
        self._retained = True

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if self.changed and not self._retained:
            _write_bytes_atomic(self.path, self.original, self.mode)
        return False


_ASSIGNMENT = re.compile(r'^\s*(?P<key>"(?:[^"\\]|\\.)*"|[A-Za-z0-9_-]+)\s*=')


def _write_bytes_atomic(path: Path, content: bytes, mode: int) -> None:
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _version_separator(value: str) -> int:
    separator = value.rfind("@")
    if value.startswith("npm:@"):
        package_separator = value.find("/", len("npm:@"))
        return separator if package_separator != -1 and separator > package_separator else -1
    return separator


def parse_add_spec(raw: str) -> AddSpec:
    if not raw or raw != raw.strip() or any(ord(character) < 33 or ord(character) == 127 for character in raw):
        raise DeclarationError(f"invalid add spec: {raw!r}")
    separator = _version_separator(raw)
    if separator > 0:
        key = raw[:separator]
        version = raw[separator + 1 :]
    else:
        key = raw
        version = "latest"
    if not key or not version or key.startswith("@") or key == "apt:" or key.startswith("apt:@"):
        raise DeclarationError(f"invalid add spec: {raw!r}")
    adapter = "apt" if key.startswith("apt:") else "mise"
    return AddSpec(raw=raw, adapter=adapter, key=key, version=version)


def _assignment_key(line: str) -> str | None:
    match = _ASSIGNMENT.match(line)
    if match is None:
        return None
    token = match.group("key")
    return json.loads(token) if token.startswith('"') else token


def _table_bounds(lines: list[str], header: str) -> tuple[int, int]:
    matching = [index for index, line in enumerate(lines) if line.strip() == header]
    if len(matching) != 1:
        raise DeclarationError(f"required TOML table is missing or duplicated: {header}")
    start = matching[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break
    return start, end


def _insertion_index(lines: list[str], start: int, end: int, key: str, *, sorted_keys: bool) -> int:
    assignments = [
        (index, parsed_key)
        for index in range(start, end)
        if (parsed_key := _assignment_key(lines[index])) is not None
    ]
    if sorted_keys:
        for index, parsed_key in assignments:
            if parsed_key > key:
                return index
    index = end
    while index > start and not lines[index - 1].strip():
        index -= 1
    return index


def _add_scalar(content: str, *, header: str, key: str, version: str, sorted_keys: bool) -> str:
    lines = content.splitlines(keepends=True)
    start, end = _table_bounds(lines, header)
    index = _insertion_index(lines, start, end, key, sorted_keys=sorted_keys)
    line = f"{json.dumps(key, ensure_ascii=False)} = {json.dumps(version, ensure_ascii=False)}\n"
    lines.insert(index, line)
    return "".join(lines)


def _append_array(content: str, *, header: str, key: str, version: str) -> str:
    lines = content.splitlines(keepends=True)
    start, end = _table_bounds(lines, header)
    for index in range(start, end):
        if _assignment_key(lines[index]) != key:
            continue
        closing = lines[index].rfind("]")
        if closing == -1:
            raise DeclarationError(f"{key} must use a single-line array before add can append a version")
        lines[index] = (
            lines[index][:closing]
            + f", {json.dumps(version, ensure_ascii=False)}"
            + lines[index][closing:]
        )
        return "".join(lines)
    raise DeclarationError(f"could not locate existing declaration: {key}")


def _table(document: dict, adapter: str) -> tuple[dict, str]:
    if adapter == "apt":
        table = document.get("bootstrap", {}).get("packages")
        header = "[bootstrap.packages]"
    else:
        table = document.get("tools")
        header = "[tools]"
    if not isinstance(table, dict):
        raise DeclarationError(f"required TOML table is missing: {header}")
    return table, header


def render_additions(content: str, specs: Iterable[AddSpec]) -> RenderedAdditions:
    requested = tuple(specs)
    try:
        document = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise DeclarationError(f"invalid mise.toml: {error}") from error

    rendered = content
    changes: list[ConfigChange] = []
    current_values = {
        "apt": dict(_table(document, "apt")[0]),
        "mise": dict(_table(document, "mise")[0]),
    }
    scopes = tuple(adapter for adapter in ("apt", "mise") if any(item.adapter == adapter for item in requested))

    for spec in requested:
        values = current_values[spec.adapter]
        current = values.get(spec.key)
        _, header = _table(document, spec.adapter)
        if current is None:
            rendered = _add_scalar(
                rendered,
                header=header,
                key=spec.key,
                version=spec.version,
                sorted_keys=spec.adapter == "apt",
            )
            values[spec.key] = spec.version
            changes.append(ConfigChange(spec.adapter, spec.key, spec.version, "add"))
        elif isinstance(current, str):
            if current != spec.version:
                raise DeclarationError(
                    f"{spec.key} is already declared as {current}; add will not replace it with {spec.version}"
                )
        elif isinstance(current, list) and all(isinstance(item, str) for item in current):
            if spec.version in current:
                continue
            rendered = _append_array(rendered, header=header, key=spec.key, version=spec.version)
            current.append(spec.version)
            changes.append(ConfigChange(spec.adapter, spec.key, spec.version, "append"))
        else:
            raise DeclarationError(f"unsupported existing declaration for {spec.key}")

    try:
        tomllib.loads(rendered)
    except tomllib.TOMLDecodeError as error:
        raise DeclarationError(f"generated invalid mise.toml: {error}") from error
    return RenderedAdditions(content=rendered, changes=tuple(changes), scopes=scopes)


def prepare_add_transaction(path: Path, raw_specs: Iterable[str]) -> AddTransaction:
    original = path.read_bytes()
    try:
        content = original.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DeclarationError(f"{path} is not valid UTF-8") from error
    mode = stat.S_IMODE(path.stat().st_mode)
    rendered = render_additions(content, (parse_add_spec(raw) for raw in raw_specs))
    return AddTransaction(path, original, mode, rendered)
