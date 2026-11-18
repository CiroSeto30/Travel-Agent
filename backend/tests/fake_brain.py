"""A fake LLM for the agent tests: scripted understanding, and replies that name the facts they were given."""

from langchain_core.messages import AIMessage

from app.agent.brain import Turn


class ScriptedBrain:
    """Returns the next scripted Turn; replies with the kind of facts it received, streamed in two tokens."""

    def __init__(self):
        self.turns: list[Turn] = []
        self.facts: list[dict] = []

    def extract(self, messages, known, catalog):
        return self.turns.pop(0)

    def reply(self, messages, facts, on_token):
        self.facts.append(facts)
        for token in ("ok: ", facts["kind"]):
            on_token(token)
        return AIMessage(f"ok: {facts['kind']}")
