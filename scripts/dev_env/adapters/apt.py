from __future__ import annotations

from dev_env.normalize import normalize_inventory, normalize_plan


class AptAdapter:
    name = "apt"
    depends_on: tuple[str, ...] = ()

    def probe(self, context):
        return normalize_inventory({}, context.bootstrap_status, context.installed_tools)["adapters"][self.name]

    def plan(self, context):
        actions = normalize_plan(context.bootstrap_status, context.bootstrap_plan)["actions"]
        return [action for action in actions if action["adapter"] == self.name]

    def apply(self, context, *, confirmed):
        context.mise.apply((self.name,), confirmed=confirmed)


ADAPTER = AptAdapter()
