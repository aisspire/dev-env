from __future__ import annotations

from typing import Any


SCHEMA_VERSION = 1


def _apt_state(bootstrap_status: dict[str, Any]) -> dict[str, Any]:
    apt = bootstrap_status.get("packages", {}).get("apt", {})
    packages = apt.get("packages", [])
    desired = [
        {"name": item["package"], "requested_version": item["requested_version"]}
        for item in packages
    ]
    observed = [
        {"name": item["package"], "version": item["installed_version"]}
        for item in packages
        if item.get("state") == "installed"
    ]
    missing = [
        {"name": item["package"], "requested_version": item["requested_version"]}
        for item in packages
        if item.get("state") != "installed"
    ]
    return {
        "status": "drift" if missing else "converged",
        "available": bool(apt.get("available", False)),
        "desired": desired,
        "observed": observed,
        "missing": missing,
        "extra": [],
        "findings": [],
    }


def _mise_state(bootstrap_status: dict[str, Any], installed_tools: dict[str, Any]) -> dict[str, Any]:
    requested = bootstrap_status.get("tools", [])
    desired = [
        {
            "tool": item["tool"],
            "requested_version": item["requested_version"],
            "resolved_version": item.get("resolved_version", ""),
        }
        for item in requested
    ]
    missing = [
        entry
        for entry, item in zip(desired, requested, strict=True)
        if item.get("state") != "installed"
    ]

    desired_versions = {
        (item["tool"], item.get("resolved_version", ""))
        for item in requested
        if item.get("state") == "installed"
    }
    observed: list[dict[str, Any]] = []
    extra: list[dict[str, str]] = []
    for tool in sorted(installed_tools):
        for item in installed_tools[tool]:
            version = str(item.get("version", ""))
            observed.append(
                {
                    "tool": tool,
                    "version": version,
                    "installed": bool(item.get("installed", True)),
                    "active": bool(item.get("active", False)),
                }
            )
            if (tool, version) not in desired_versions:
                extra.append({"tool": tool, "version": version})

    findings = []
    for item in bootstrap_status.get("dotfiles", {}).get("files", []):
        state = str(item.get("state", "unknown"))
        if state != "applied":
            findings.append(
                {
                    "code": f"mise.dotfile.{state}",
                    "severity": "warning",
                    "message": f"{item.get('target', 'dotfile')} is {state}",
                }
            )
    for item in bootstrap_status.get("mise_shell_activate", []):
        if item.get("state") != "applied":
            findings.append(
                {
                    "code": "mise.shell_activation.missing",
                    "severity": "warning",
                    "message": f"{item.get('target', 'shell')} activation is {item.get('state', 'unknown')}",
                }
            )

    return {
        "status": "drift" if missing or findings else "converged",
        "desired": desired,
        "observed": observed,
        "missing": missing,
        "extra": extra,
        "findings": findings,
    }


def normalize_inventory(
    platform: dict[str, Any],
    bootstrap_status: dict[str, Any],
    installed_tools: dict[str, Any],
) -> dict[str, Any]:
    apt = _apt_state(bootstrap_status)
    mise = _mise_state(bootstrap_status, installed_tools)
    missing_count = len(apt["missing"]) + len(mise["missing"])
    extra_count = len(apt["extra"]) + len(mise["extra"])
    findings_count = len(apt["findings"]) + len(mise["findings"])
    converged = apt["status"] == "converged" and mise["status"] == "converged"
    return {
        "schema_version": SCHEMA_VERSION,
        "platform": platform,
        "adapters": {"apt": apt, "mise": mise},
        "summary": {
            "converged": converged,
            "missing": missing_count,
            "extra": extra_count,
            "findings": findings_count,
        },
    }


def normalize_plan(bootstrap_status: dict[str, Any], bootstrap_plan: dict[str, Any]) -> dict[str, Any]:
    actions: list[dict[str, str]] = []
    for resource in bootstrap_plan.get("resources", []):
        action = resource.get("action")
        identifier = resource.get("id", {})
        if action in {"noop", "remove"}:
            continue
        name = str(identifier.get("name", ""))
        adapter = "apt" if name.startswith("apt:") else "mise"
        actions.append(
            {
                "adapter": adapter,
                "kind": str(identifier.get("kind", "resource")),
                "name": name,
                "action": str(action),
                "current": str(resource.get("current", "unknown")),
                "desired": str(resource.get("desired", "unknown")),
            }
        )

    action_keys = {(item["kind"], item["name"]) for item in actions}
    for item in bootstrap_status.get("dotfiles", {}).get("files", []):
        state = str(item.get("state", "unknown"))
        name = str(item.get("target", "dotfile"))
        if state != "applied" and ("dotfile", name) not in action_keys:
            actions.append(
                {
                    "adapter": "mise",
                    "kind": "dotfile",
                    "name": name,
                    "action": "repair",
                    "current": state,
                    "desired": str(item.get("mode", "managed")),
                }
            )

    for item in bootstrap_status.get("mise_shell_activate", []):
        if item.get("state") != "applied":
            actions.append(
                {
                    "adapter": "mise",
                    "kind": "shell_activation",
                    "name": str(item.get("target", "shell")),
                    "action": "repair",
                    "current": str(item.get("state", "unknown")),
                    "desired": str(item.get("mode", "activate")),
                }
            )

    for item in bootstrap_status.get("tools", []):
        if item.get("state") != "installed":
            requested = str(item.get("requested_version", ""))
            actions.append(
                {
                    "adapter": "mise",
                    "kind": "tool",
                    "name": f"{item.get('tool', '')}@{requested}",
                    "action": "create",
                    "current": str(item.get("state", "missing")),
                    "desired": str(item.get("resolved_version", requested)),
                }
            )

    actions.sort(key=lambda item: ({"apt": 0, "mise": 1}.get(item["adapter"], 2), item["kind"], item["name"]))
    summary = {
        "create": sum(1 for item in actions if item["action"] == "create"),
        "repair": sum(1 for item in actions if item["action"] == "repair"),
        "total": len(actions),
    }
    return {"schema_version": SCHEMA_VERSION, "actions": actions, "summary": summary}
