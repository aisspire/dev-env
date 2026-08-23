from __future__ import annotations


class RustupAdapter:
    name = "rustup"
    depends_on = ("mise",)

    def probe(self, context):
        return context.rustup.status()

    def plan(self, context):
        return context.rustup.plan()

    def apply(self, context, *, confirmed):
        context.rustup.apply(confirmed=confirmed)


ADAPTER = RustupAdapter()
