"""Bloom's Grid wire protocol (payloads are JSON strings, version 1)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

VERSION = 1
MAX_CONTEXT_CHARS = 9000
MAX_PAYLOAD_CHARS = 32000


@dataclass
class Step:
    """One unit of work sent from the orchestrator to a specialist."""

    job_id: str
    step_id: str
    specialist: str
    instruction: str
    context: list[dict] = field(default_factory=list)  # [{"from": slug, "output": text}]
    spec: dict | None = None
    depends_on: list[str] = field(default_factory=list)

    def to_payload(self) -> str:
        ctx = [{"from": c.get("from", "?"), "output": str(c.get("output", ""))[:MAX_CONTEXT_CHARS]}
               for c in self.context]
        body = {"bloom": VERSION, "kind": "step", **asdict(self), "context": ctx}
        body.pop("depends_on", None)
        text = json.dumps(body)
        if len(text) > MAX_PAYLOAD_CHARS:
            body["spec"] = None
            text = json.dumps(body)[:MAX_PAYLOAD_CHARS]
        return text

    @classmethod
    def from_payload(cls, payload: str) -> "Step":
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get("bloom") != VERSION or data.get("kind") != "step":
            raise ValueError("Not a Bloom step payload")
        return cls(
            job_id=str(data["job_id"]),
            step_id=str(data["step_id"]),
            specialist=str(data["specialist"]),
            instruction=str(data["instruction"]),
            context=list(data.get("context") or []),
            spec=data.get("spec"),
        )


@dataclass
class Result:
    """A specialist's reply."""

    job_id: str
    step_id: str
    specialist: str
    ok: bool
    output: str = ""
    answer: str | None = None
    error: str | None = None
    checked: bool = False  # a self-check pass ran
    changed: bool = False  # the self-check changed the answer
    trace: list = field(default_factory=list)  # timed model/tool spans (bloom.trace)
    usage: dict = field(default_factory=dict)  # tokens, call counts, ms
    model: str = ""

    def to_payload(self) -> str:
        body = {"bloom": VERSION, "kind": "result", **asdict(self)}
        body["output"] = ""
        room = MAX_PAYLOAD_CHARS - len(json.dumps(body)) - 200
        if room < 2000:  # keep the answer; drop trace detail before the output
            body["trace"] = body["trace"][:10]
            room = MAX_PAYLOAD_CHARS - len(json.dumps(body)) - 200
        body["output"] = self.output[: max(0, room)]
        return json.dumps(body)

    @classmethod
    def from_payload(cls, payload: str) -> "Result":
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get("kind") != "result":
            raise ValueError("Not a Bloom result payload")
        return cls(
            job_id=str(data.get("job_id", "")),
            step_id=str(data.get("step_id", "")),
            specialist=str(data.get("specialist", "")),
            ok=bool(data.get("ok")),
            output=str(data.get("output") or ""),
            answer=data.get("answer"),
            error=data.get("error"),
            checked=bool(data.get("checked", False)),
            changed=bool(data.get("changed", False)),
            trace=list(data.get("trace") or []),
            usage=dict(data.get("usage") or {}),
            model=str(data.get("model") or ""),
        )


def parse_grid_prompt(prompt: str) -> dict | None:
    """If the AgentApp prompt is a Grid message ({message_id, src_node_id, payload}), return it."""
    try:
        data = json.loads(prompt)
    except (TypeError, ValueError):
        return None
    if isinstance(data, dict) and "src_node_id" in data and "payload" in data:
        return data
    return None


# ── discovery ────────────────────────────────────────────────────────────────
def describe_payload(job_id: str = "") -> str:
    """Orchestrator -> node: 'what can you do?' (empty body)."""
    return json.dumps({"bloom": VERSION, "kind": "describe", "job_id": job_id})


def is_describe(payload: str) -> bool:
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return False
    return isinstance(data, dict) and data.get("kind") == "describe"


@dataclass
class Capabilities:
    """Node -> orchestrator reply to describe."""

    specialist: str | None
    category: str | None = None
    purpose: str = ""
    tools: list = field(default_factory=list)
    model: str = ""
    has_db: bool = False
    node_name: str | None = None
    approved: bool = True  # False: this node would refuse to run its specialist
    spec_sha256: str | None = None
    inbox: bool = False  # the owner opted this node in to receive proposals over the Grid
    site: str | None = None  # e.g. "Hospital A": whose private data this node holds

    def to_payload(self) -> str:
        return json.dumps({"bloom": VERSION, "kind": "capabilities", **asdict(self)})

    @classmethod
    def from_payload(cls, payload: str) -> "Capabilities":
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get("kind") != "capabilities":
            raise ValueError("Not a Bloom capabilities payload")
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__ if k in data})


# ── proposal delivery (Forge -> node owner's inbox, over the Grid) ─────────────
MAX_PROPOSAL_CHARS = 200_000


def proposal_payload(proposal: dict, sender: str) -> str:
    return json.dumps({"bloom": VERSION, "kind": "proposal", "from": sender, "proposal": proposal})


def parse_kind(payload: str) -> tuple[str | None, dict]:
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return None, {}
    return (data.get("kind"), data) if isinstance(data, dict) else (None, {})
