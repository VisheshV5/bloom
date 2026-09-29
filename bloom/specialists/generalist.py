"""Bloom's starting agent: a generalist with no tools. Hand-written."""

from bloom.specialists import default_postprocess

SLUG = "generalist"
CATEGORY = None
PURPOSE = "Answers any question directly, without tools."
MODEL = "openai/gpt-5.6-sol"
TOOLS: list[str] = []
INSTRUCTIONS = (
    "You are the generalist agent of the Bloom team. Answer the user's question as "
    "accurately as you can using your own knowledge and reasoning. You have no tools "
    "and no database access. Be concise. Always end with a line `FINAL: <answer>`."
)
VERIFY = ""  # the generalist does not self-check
EXAMPLES: list[list[str]] = []


def postprocess(text: str) -> str | None:
    return default_postprocess(text)
