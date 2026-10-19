"""Two or more clients behind one: most residents on a local open-weight model, a few on a hosted one.

``MixedClient`` picks the client by the model id the router chose. A model id with no entry
goes to the default client. Pair it with ``LLMConfig.agent_models`` to give particular
residents a particular model.
"""


class MixedClient:
    def __init__(self, default, by_model: dict | None = None) -> None:
        self.default = default
        self.by_model = dict(by_model or {})
        self.counts: dict[str, int] = {}

    def client_for(self, model: str):
        return self.by_model.get(model, self.default)

    async def complete(self, request, model, effort):
        self.counts[model] = self.counts.get(model, 0) + 1
        return await self.client_for(model).complete(request, model, effort)
