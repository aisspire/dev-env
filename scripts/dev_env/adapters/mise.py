from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from dev_env.normalize import normalize_inventory, normalize_plan


MANAGED_BLOCK_START = "# >>> mise:activate >>>"
MANAGED_BLOCK_END = "# <<< mise:activate <<<"
LEGACY_BASH_ACTIVATION = 'eval "$(mise activate bash)"'


def deduplicate_legacy_activation(content: str) -> str:
    if MANAGED_BLOCK_START not in content or MANAGED_BLOCK_END not in content:
        return content

    migrated: list[str] = []
    inside_managed_block = False
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(MANAGED_BLOCK_START):
            inside_managed_block = True
            migrated.append(line)
        elif stripped.startswith(MANAGED_BLOCK_END):
            migrated.append(line)
            inside_managed_block = False
        elif not inside_managed_block and stripped == LEGACY_BASH_ACTIVATION:
            continue
        else:
            migrated.append(line)
    return "".join(migrated)


def repair_legacy_bashrc(path: Path | None = None) -> bool:
    target = path or Path.home() / ".bashrc"
    if not target.exists():
        return False
    original = target.read_text(encoding="utf-8")
    migrated = deduplicate_legacy_activation(original)
    if migrated == original:
        return False

    mode = stat.S_IMODE(target.stat().st_mode)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(migrated)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, target)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return True


class MiseAdapter:
    name = "mise"
    depends_on = ("apt",)

    def probe(self, context):
        return normalize_inventory({}, context.bootstrap_status, context.installed_tools)["adapters"][self.name]

    def plan(self, context):
        actions = normalize_plan(context.bootstrap_status, context.bootstrap_plan)["actions"]
        return [action for action in actions if action["adapter"] == self.name]

    def apply(self, context, *, confirmed):
        context.mise.apply((self.name,), confirmed=confirmed)
        repair_legacy_bashrc()


ADAPTER = MiseAdapter()
