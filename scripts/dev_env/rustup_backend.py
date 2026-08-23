from __future__ import annotations

import hashlib
import hmac
import os
import platform
import re
import shutil
import tempfile
import tomllib
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .runner import CommandError, CommandRunner
from .rustup_config import RustupConfig, RustupToolchain, load_rustup_config


RUSTUP_DIST_ROOT = "https://static.rust-lang.org/rustup/dist"
INSTALLER_TARGETS = {
    "aarch64": "aarch64-unknown-linux-gnu",
    "arm64": "aarch64-unknown-linux-gnu",
    "amd64": "x86_64-unknown-linux-gnu",
    "x86_64": "x86_64-unknown-linux-gnu",
}
PROFILE_COMPONENTS = {
    "minimal": frozenset({"cargo", "rust-std", "rustc"}),
    "default": frozenset({"cargo", "clippy", "rust-docs", "rust-std", "rustc", "rustfmt"}),
}


class RustupError(RuntimeError):
    pass


def _download_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "dev-env-rustup-adapter/1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


class RustupBackend:
    def __init__(
        self,
        repo_root: Path,
        runner: CommandRunner,
        *,
        rustup_binary: str | None = None,
        cargo_home: Path | None = None,
        rustup_home: Path | None = None,
        env: Mapping[str, str] | None = None,
        binary_finder: Callable[[str], str | None] | None = None,
        architecture_probe: Callable[[], str] = platform.machine,
        downloader: Callable[[str], bytes] = _download_bytes,
    ) -> None:
        self.repo_root = repo_root
        self.runner = runner
        self._configured_binary = rustup_binary
        self._base_env = dict(os.environ if env is None else env)
        self.cargo_home = cargo_home or Path(
            self._base_env.get("CARGO_HOME") or Path.home() / ".cargo"
        )
        self.rustup_home = rustup_home or Path(
            self._base_env.get("RUSTUP_HOME") or Path.home() / ".rustup"
        )
        self._binary_finder = binary_finder or (
            lambda name: shutil.which(name, path=self._base_env.get("PATH"))
        )
        self._architecture_probe = architecture_probe
        self._downloader = downloader

    @property
    def config_path(self) -> Path:
        return self.repo_root / "rustup.toml"

    def load_config(self) -> RustupConfig:
        return load_rustup_config(self.config_path)

    def _env(self) -> dict[str, str]:
        env = self._base_env.copy()
        env["CARGO_HOME"] = str(self.cargo_home)
        env["RUSTUP_HOME"] = str(self.rustup_home)
        env["RUSTUP_AUTO_INSTALL"] = "0"
        env["RUSTUP_TERM_COLOR"] = "never"
        return env

    def _rustup_binary(self) -> str | None:
        if self._configured_binary is not None:
            return self._configured_binary
        discovered = self._binary_finder("rustup")
        if discovered:
            return discovered
        expected = self.cargo_home / "bin" / "rustup"
        if expected.is_file() and os.access(expected, os.X_OK):
            return str(expected)
        return None

    def _require_rustup_binary(self) -> str:
        binary = self._rustup_binary()
        if binary is None:
            raise RustupError("rustup is not installed")
        return binary

    def _capture(self, binary: str, *arguments: str) -> str:
        completed = self.runner.run(
            [binary, *arguments],
            cwd=self.repo_root,
            env=self._env(),
        )
        return completed.stdout

    def _run_interactive(self, binary: str, *arguments: str) -> None:
        self.runner.run_interactive(
            [binary, *arguments],
            cwd=self.repo_root,
            env=self._env(),
        )

    def _settings(self) -> tuple[dict[str, Any], bool]:
        path = self.rustup_home / "settings.toml"
        try:
            with path.open("rb") as settings_file:
                document = tomllib.load(settings_file)
        except FileNotFoundError:
            return {}, True
        except (OSError, tomllib.TOMLDecodeError):
            return {}, False
        return document if isinstance(document, dict) else {}, isinstance(document, dict)

    @staticmethod
    def _manager_version(output: str) -> str:
        for line in output.splitlines():
            match = re.match(r"^rustup\s+([^\s]+)", line.strip())
            if match is not None:
                return match.group(1)
        raise RustupError("could not parse rustup manager version")

    @staticmethod
    def _toolchain_rows(output: str) -> list[tuple[str, frozenset[str]]]:
        rows: list[tuple[str, frozenset[str]]] = []
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped or stripped.lower().startswith("no installed toolchains"):
                continue
            name, separator, annotation = stripped.partition(" (")
            flags = frozenset(
                item.strip()
                for item in annotation.removesuffix(")").split(",")
                if separator and item.strip()
            )
            rows.append((name.strip(), flags))
        return rows

    @staticmethod
    def _default_host(output: str) -> str:
        for line in output.splitlines():
            label, separator, value = line.partition(":")
            if separator and label.strip().lower() == "default host":
                return value.strip()
        return ""

    @staticmethod
    def _normalize_toolchain(name: str, host: str) -> str:
        suffix = f"-{host}" if host else ""
        if suffix and name.endswith(suffix):
            return name[: -len(suffix)]
        return name

    @staticmethod
    def _rustc_details(output: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for line in output.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                fields[key.strip().lower().replace("-", "_")] = value.strip()
        release = fields.get("release", "")
        commit_date = fields.get("commit_date", "")
        if not release or not commit_date:
            raise RustupError("could not parse rustc release and commit date")
        return {
            "release": release,
            "commit_date": commit_date,
            "host": fields.get("host", ""),
        }

    @staticmethod
    def _installed_names(output: str, host: str, *, strip_host: bool) -> list[str]:
        names: list[str] = []
        suffix = f"-{host}" if host else ""
        for line in output.splitlines():
            name = line.strip().split(maxsplit=1)[0] if line.strip() else ""
            if not name:
                continue
            if strip_host and suffix and name.endswith(suffix):
                name = name[: -len(suffix)]
            names.append(name)
        return sorted(set(names))

    def _inspect_toolchain(
        self,
        binary: str,
        raw_name: str,
        canonical_name: str,
        default_host: str,
        *,
        strict: bool,
    ) -> dict[str, Any]:
        try:
            details = self._rustc_details(
                self._capture(binary, "run", raw_name, "rustc", "--version", "--verbose")
            )
        except (CommandError, RustupError):
            if strict:
                raise
            details = {"release": "", "commit_date": "", "host": default_host}

        host = details["host"] or default_host
        try:
            components = self._installed_names(
                self._capture(
                    binary,
                    "component",
                    "list",
                    "--installed",
                    "--toolchain",
                    raw_name,
                ),
                host,
                strip_host=True,
            )
        except CommandError:
            if strict:
                raise
            components = []
        try:
            targets = self._installed_names(
                self._capture(
                    binary,
                    "target",
                    "list",
                    "--installed",
                    "--toolchain",
                    raw_name,
                ),
                host,
                strip_host=False,
            )
        except CommandError:
            if strict:
                raise
            targets = []

        cross_target_components = {f"rust-std-{target}" for target in targets}
        components = [
            component
            for component in components
            if component not in cross_target_components
        ]

        return {
            "toolchain": canonical_name,
            "release": details["release"],
            "commit_date": details["commit_date"],
            "host": host,
            "components": components,
            "targets": targets,
        }

    @staticmethod
    def _desired(config: RustupConfig) -> list[dict[str, Any]]:
        return [
            {
                "toolchain": toolchain.name,
                "default": toolchain.name == config.default_toolchain,
                "profile": config.profile,
                "components": list(toolchain.components),
                "targets": list(toolchain.targets),
            }
            for toolchain in config.toolchains
        ]

    @staticmethod
    def _finding(code: str, message: str) -> dict[str, str]:
        return {"code": code, "severity": "warning", "message": message}

    def status(self, config: RustupConfig | None = None) -> dict[str, Any]:
        desired_config = config or self.load_config()
        desired = self._desired(desired_config)
        binary = self._rustup_binary()
        if binary is None:
            missing = [{"kind": "manager", "name": "rustup"}]
            missing.extend(
                {"kind": "toolchain", "toolchain": toolchain.name}
                for toolchain in desired_config.toolchains
            )
            findings = [
                self._finding(
                    "rustup.profile.mismatch",
                    f"rustup profile is missing; expected {desired_config.profile}",
                ),
                self._finding(
                    "rustup.default_toolchain.mismatch",
                    f"rustup default toolchain is missing; expected {desired_config.default_toolchain}",
                ),
            ]
            return {
                "status": "drift",
                "available": False,
                "manager": {"version": ""},
                "default_toolchain": {
                    "desired": desired_config.default_toolchain,
                    "observed": "",
                },
                "profile": {"desired": desired_config.profile, "observed": ""},
                "desired": desired,
                "observed": [],
                "missing": missing,
                "extra": [],
                "findings": findings,
            }

        manager_version = self._manager_version(self._capture(binary, "--version"))
        rows = self._toolchain_rows(self._capture(binary, "toolchain", "list"))
        settings, settings_valid = self._settings()
        try:
            show_output = self._capture(binary, "show")
        except CommandError:
            show_output = ""
        default_host = self._default_host(show_output)
        if not default_host:
            default_host = INSTALLER_TARGETS.get(
                self._architecture_probe().strip().lower(),
                "",
            )

        normalized_rows = [
            (raw_name, self._normalize_toolchain(raw_name, default_host), flags)
            for raw_name, flags in rows
        ]
        marker_default = next(
            (canonical for _, canonical, flags in normalized_rows if "default" in flags),
            "",
        )
        raw_default = settings.get("default_toolchain", marker_default)
        if not isinstance(raw_default, str) or raw_default == "none":
            raw_default = ""
        observed_default = self._normalize_toolchain(raw_default, default_host)
        raw_profile = settings.get("profile", "default")
        observed_profile = raw_profile if isinstance(raw_profile, str) else "default"

        desired_names = {toolchain.name for toolchain in desired_config.toolchains}
        observed_by_name: dict[str, dict[str, Any]] = {}
        for raw_name, canonical_name, _ in normalized_rows:
            observed_by_name[canonical_name] = self._inspect_toolchain(
                binary,
                raw_name,
                canonical_name,
                default_host,
                strict=canonical_name in desired_names,
            )

        observed = [
            observed_by_name[name]
            for name in [toolchain.name for toolchain in desired_config.toolchains]
            if name in observed_by_name
        ]
        observed.extend(
            observed_by_name[name]
            for name in sorted(set(observed_by_name) - desired_names)
        )

        missing: list[dict[str, str]] = []
        extra: list[dict[str, str]] = []
        for toolchain in desired_config.toolchains:
            current = observed_by_name.get(toolchain.name)
            if current is None:
                missing.append({"kind": "toolchain", "toolchain": toolchain.name})
                continue
            installed_components = set(current["components"])
            installed_targets = set(current["targets"])
            missing.extend(
                {
                    "kind": "component",
                    "toolchain": toolchain.name,
                    "name": component,
                }
                for component in toolchain.components
                if component not in installed_components
            )
            missing.extend(
                {"kind": "target", "toolchain": toolchain.name, "name": target}
                for target in toolchain.targets
                if target not in installed_targets
            )

            implicit_components = PROFILE_COMPONENTS.get(desired_config.profile, frozenset())
            if desired_config.profile == "complete":
                implicit_components = frozenset(installed_components)
            extra.extend(
                {
                    "kind": "component",
                    "toolchain": toolchain.name,
                    "name": component,
                }
                for component in sorted(
                    installed_components - set(toolchain.components) - set(implicit_components)
                )
            )
            native_target = current["host"] or default_host
            extra.extend(
                {"kind": "target", "toolchain": toolchain.name, "name": target}
                for target in sorted(
                    installed_targets - set(toolchain.targets) - ({native_target} if native_target else set())
                )
            )

        extra.extend(
            {"kind": "toolchain", "toolchain": name}
            for name in sorted(set(observed_by_name) - desired_names)
        )

        findings: list[dict[str, str]] = []
        if not settings_valid:
            findings.append(
                self._finding(
                    "rustup.settings.invalid",
                    "rustup settings could not be read as TOML",
                )
            )
        if observed_profile != desired_config.profile:
            findings.append(
                self._finding(
                    "rustup.profile.mismatch",
                    f"rustup profile is {observed_profile or 'missing'}; expected {desired_config.profile}",
                )
            )
        if observed_default != desired_config.default_toolchain:
            findings.append(
                self._finding(
                    "rustup.default_toolchain.mismatch",
                    "rustup default toolchain is "
                    f"{observed_default or 'missing'}; expected {desired_config.default_toolchain}",
                )
            )

        return {
            "status": "drift" if missing or findings else "converged",
            "available": True,
            "manager": {"version": manager_version},
            "default_toolchain": {
                "desired": desired_config.default_toolchain,
                "observed": observed_default,
            },
            "profile": {"desired": desired_config.profile, "observed": observed_profile},
            "desired": desired,
            "observed": observed,
            "missing": missing,
            "extra": extra,
            "findings": findings,
        }

    @staticmethod
    def _action(
        kind: str,
        name: str,
        action: str,
        current: str,
        desired: str,
    ) -> dict[str, str]:
        return {
            "adapter": "rustup",
            "kind": kind,
            "name": name,
            "action": action,
            "current": current,
            "desired": desired,
        }

    @staticmethod
    def _toolchain_description(config: RustupConfig, toolchain: RustupToolchain) -> str:
        components = ",".join(toolchain.components) or "profile-only"
        targets = ",".join(toolchain.targets) or "native-only"
        return f"installed (profile={config.profile}; components={components}; targets={targets})"

    def plan(self) -> list[dict[str, str]]:
        config = self.load_config()
        state = self.status(config)
        actions: list[dict[str, str]] = []
        if not state["available"]:
            actions.append(self._action("manager", "rustup", "create", "missing", "installed"))

        if state["profile"]["observed"] != config.profile:
            actions.append(
                self._action(
                    "profile",
                    config.profile,
                    "repair",
                    state["profile"]["observed"] or "missing",
                    config.profile,
                )
            )

        missing_toolchains = {
            item["toolchain"]
            for item in state["missing"]
            if item["kind"] == "toolchain"
        }
        for toolchain in config.toolchains:
            if toolchain.name in missing_toolchains:
                actions.append(
                    self._action(
                        "toolchain",
                        toolchain.name,
                        "create",
                        "missing",
                        self._toolchain_description(config, toolchain),
                    )
                )

        for item in state["missing"]:
            if item["kind"] not in {"component", "target"}:
                continue
            actions.append(
                self._action(
                    item["kind"],
                    f"{item['toolchain']}:{item['name']}",
                    "create",
                    "missing",
                    "installed",
                )
            )

        if state["default_toolchain"]["observed"] != config.default_toolchain:
            actions.append(
                self._action(
                    "default_toolchain",
                    config.default_toolchain,
                    "repair",
                    state["default_toolchain"]["observed"] or "missing",
                    config.default_toolchain,
                )
            )
        return actions

    def _installer_target(self) -> str:
        architecture = self._architecture_probe().strip().lower()
        try:
            return INSTALLER_TARGETS[architecture]
        except KeyError as error:
            raise RustupError(f"unsupported architecture for rustup installer: {architecture or 'unknown'}") from error

    def _foreign_rust_commands(self) -> list[tuple[str, str]]:
        conflicts: list[tuple[str, str]] = []
        seen: set[str] = set()
        for name in ("rustc", "cargo"):
            candidates = [self._binary_finder(name), str(self.cargo_home / "bin" / name)]
            for path in candidates:
                if not path:
                    continue
                normalized = os.path.abspath(path)
                if normalized in seen:
                    continue
                if path == candidates[1] and not os.path.lexists(path):
                    continue
                seen.add(normalized)
                conflicts.append((name, path))
        return conflicts

    def _install_manager(self, profile_name: str, installer_target: str) -> None:
        conflicts = self._foreign_rust_commands()
        if conflicts:
            rendered = ", ".join(f"{name}={path}" for name, path in conflicts)
            raise RustupError(
                "existing Rust commands are not owned by rustup; refusing to overwrite: "
                f"{rendered}"
            )

        installer_url = f"{RUSTUP_DIST_ROOT}/{installer_target}/rustup-init"
        checksum_url = f"{installer_url}.sha256"
        with tempfile.TemporaryDirectory(prefix="dev-env-rustup-") as directory:
            temporary = Path(directory)
            installer = temporary / "rustup-init"
            checksum_file = temporary / "rustup-init.sha256"
            payload = self._downloader(installer_url)
            checksum_payload = self._downloader(checksum_url)
            installer.write_bytes(payload)
            checksum_file.write_bytes(checksum_payload)

            try:
                expected = checksum_payload.decode("ascii").strip().split()[0].lower()
            except (UnicodeDecodeError, IndexError) as error:
                raise RustupError("invalid rustup-init SHA256 file") from error
            if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
                raise RustupError("invalid rustup-init SHA256 file")
            observed = hashlib.sha256(payload).hexdigest()
            if not hmac.compare_digest(observed, expected):
                raise RustupError("rustup-init SHA256 mismatch")

            os.chmod(installer, 0o700)
            self.runner.run_interactive(
                [
                    str(installer),
                    "-y",
                    "--no-modify-path",
                    "--default-toolchain",
                    "none",
                    "--profile",
                    profile_name,
                ],
                cwd=self.repo_root,
                env=self._env(),
            )

        installed_binary = self.cargo_home / "bin" / "rustup"
        if not installed_binary.is_file() or not os.access(installed_binary, os.X_OK):
            raise RustupError("rustup-init completed without installing the rustup executable")
        self._configured_binary = str(installed_binary)

    def _install_toolchain(
        self,
        binary: str,
        config: RustupConfig,
        toolchain: RustupToolchain,
    ) -> None:
        arguments = ["toolchain", "install", toolchain.name, "--profile", config.profile]
        for component in toolchain.components:
            arguments.extend(("--component", component))
        for target in toolchain.targets:
            arguments.extend(("--target", target))
        if toolchain.name == "nightly":
            arguments.append("--allow-downgrade")
        arguments.append("--no-self-update")
        self._run_interactive(binary, *arguments)

    def _repair_toolchain(
        self,
        binary: str,
        config: RustupConfig,
        toolchain: RustupToolchain,
        state: dict[str, Any],
    ) -> None:
        observed = next(
            (item for item in state["observed"] if item["toolchain"] == toolchain.name),
            None,
        )
        if observed is None:
            self._install_toolchain(binary, config, toolchain)
            return

        installed_components = set(observed["components"])
        missing_components = [
            component
            for component in toolchain.components
            if component not in installed_components
        ]
        if missing_components:
            self._run_interactive(
                binary,
                "component",
                "add",
                *missing_components,
                "--toolchain",
                toolchain.name,
            )

        installed_targets = set(observed["targets"])
        missing_targets = [target for target in toolchain.targets if target not in installed_targets]
        if missing_targets:
            self._run_interactive(
                binary,
                "target",
                "add",
                *missing_targets,
                "--toolchain",
                toolchain.name,
            )

    def apply(self, *, confirmed: bool) -> None:
        if not confirmed:
            raise RustupError("rustup apply requires prior confirmation")

        config = self.load_config()
        state = self.status(config)
        if not state["available"]:
            installer_target = self._installer_target()
            self._install_manager(config.profile, installer_target)
            state = self.status(config)

        binary = self._require_rustup_binary()
        if state["profile"]["observed"] != config.profile:
            self._run_interactive(binary, "set", "profile", config.profile)

        default_toolchain = config.toolchain(config.default_toolchain)
        self._repair_toolchain(binary, config, default_toolchain, state)
        if state["default_toolchain"]["observed"] != config.default_toolchain:
            self._run_interactive(binary, "default", config.default_toolchain)

        for toolchain in config.toolchains:
            if toolchain.name != config.default_toolchain:
                self._repair_toolchain(binary, config, toolchain, state)
