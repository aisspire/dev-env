from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path


SCHEMA_VERSION = 1
PROFILES = frozenset({"minimal", "default", "complete"})


class RustupConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RustupToolchain:
    name: str
    components: tuple[str, ...]
    targets: tuple[str, ...]


@dataclass(frozen=True)
class RustupConfig:
    schema_version: int
    default_toolchain: str
    profile: str
    toolchains: tuple[RustupToolchain, ...]

    def toolchain(self, name: str) -> RustupToolchain:
        for toolchain in self.toolchains:
            if toolchain.name == name:
                return toolchain
        raise KeyError(name)


_VERSIONED_CHANNEL = r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:-beta(?:\.[0-9]+)?)?"
_TOOLCHAIN_NAME = re.compile(
    rf"(?P<channel>stable|beta|nightly|{_VERSIONED_CHANNEL})(?:-(?P<date>[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}))?"
)
_COMPONENT_NAME = re.compile(r"[a-z][a-z0-9-]*")
_TARGET_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]*")


def _require_exact_keys(table: dict, expected: set[str], location: str) -> None:
    missing = expected - set(table)
    extra = set(table) - expected
    if missing:
        raise RustupConfigError(f"{location} is missing required key(s): {', '.join(sorted(missing))}")
    if extra:
        raise RustupConfigError(f"{location} has unknown key(s): {', '.join(sorted(extra))}")


def _require_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise RustupConfigError(f"{location} must be a non-empty string")
    return value


def _validate_toolchain_name(value: object, location: str) -> str:
    name = _require_string(value, location)
    match = _TOOLCHAIN_NAME.fullmatch(name)
    if match is None:
        raise RustupConfigError(f"{location} is not a safe official Rust toolchain name: {name!r}")
    if match.group("date") is not None:
        try:
            date.fromisoformat(match.group("date"))
        except ValueError as error:
            raise RustupConfigError(f"{location} contains an invalid date: {name!r}") from error
    return name


def _validate_unique_names(
    value: object,
    location: str,
    pattern: re.Pattern[str],
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RustupConfigError(f"{location} must be an array")
    names: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        name = _require_string(item, f"{location}[{index}]")
        if pattern.fullmatch(name) is None:
            raise RustupConfigError(f"{location}[{index}] is not a safe name: {name!r}")
        if name in seen:
            raise RustupConfigError(f"{location} contains duplicate value: {name}")
        seen.add(name)
        names.append(name)
    return tuple(names)


def parse_rustup_config(document: object) -> RustupConfig:
    if not isinstance(document, dict):
        raise RustupConfigError("rustup.toml must contain a TOML document")
    _require_exact_keys(
        document,
        {"schema_version", "default_toolchain", "profile", "toolchains"},
        "rustup.toml",
    )

    schema_version = document["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise RustupConfigError("schema_version must be an integer")
    if schema_version != SCHEMA_VERSION:
        raise RustupConfigError(
            f"unsupported rustup.toml schema_version: {schema_version}; expected {SCHEMA_VERSION}"
        )

    default_toolchain = _validate_toolchain_name(
        document["default_toolchain"],
        "default_toolchain",
    )
    profile = _require_string(document["profile"], "profile")
    if profile not in PROFILES:
        raise RustupConfigError(
            f"profile must be one of: {', '.join(sorted(PROFILES))}"
        )

    toolchain_table = document["toolchains"]
    if not isinstance(toolchain_table, dict) or not toolchain_table:
        raise RustupConfigError("toolchains must be a non-empty table")

    toolchains: list[RustupToolchain] = []
    for raw_name, raw_spec in toolchain_table.items():
        name = _validate_toolchain_name(raw_name, f"toolchains.{raw_name}")
        if not isinstance(raw_spec, dict):
            raise RustupConfigError(f"toolchains.{name} must be a table")
        _require_exact_keys(raw_spec, {"components", "targets"}, f"toolchains.{name}")
        toolchains.append(
            RustupToolchain(
                name=name,
                components=_validate_unique_names(
                    raw_spec["components"],
                    f"toolchains.{name}.components",
                    _COMPONENT_NAME,
                ),
                targets=_validate_unique_names(
                    raw_spec["targets"],
                    f"toolchains.{name}.targets",
                    _TARGET_NAME,
                ),
            )
        )

    declared_names = {toolchain.name for toolchain in toolchains}
    if default_toolchain not in declared_names:
        raise RustupConfigError(
            f"default_toolchain {default_toolchain!r} is not declared in toolchains"
        )

    return RustupConfig(
        schema_version=schema_version,
        default_toolchain=default_toolchain,
        profile=profile,
        toolchains=tuple(toolchains),
    )


def load_rustup_config(path: Path) -> RustupConfig:
    try:
        with path.open("rb") as config_file:
            document = tomllib.load(config_file)
    except OSError as error:
        raise RustupConfigError(f"cannot read rustup config: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise RustupConfigError(f"invalid rustup.toml: {error}") from error
    return parse_rustup_config(document)
