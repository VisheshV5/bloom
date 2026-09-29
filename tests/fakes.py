"""Fakes for the OpenAI client and the Flower Grid (shapes match flwr 1.39 grid.py)."""

from __future__ import annotations

import itertools
import json

from bloom.local_session import LocalAgent


class _Item:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return dict(self._d)


class _Response:
    def __init__(self, text="", calls=()):
        self.output_text = text
        items = [{"type": "function_call", "call_id": f"c{i}", "name": n, "arguments": json.dumps(a)}
                 for i, (n, a) in enumerate(calls)]
        if text:
            items.append({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]})
        self.output = [_Item(i) for i in items]


class FakeClient:
    """responder(kwargs) -> str | (tool_name, args) list. Records every request."""

    def __init__(self, responder=None, raise_exc=None):
        self.responder = responder or (lambda kw: "Thinking.\nFINAL: 42")
        self.raise_exc = raise_exc
        self.requests: list[dict] = []
        self.responses = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.raise_exc:
            raise self.raise_exc
        out = self.responder(kwargs)
        if isinstance(out, list):
            return _Response(calls=out)
        return _Response(text=out)


class NodeGrid:
    """SuperNode-side grid: only push_reply_message."""

    def __init__(self):
        self.replies: list[str] = []

    def tools(self):
        return [{"name": "push_reply_message"}]

    def call(self, tool_call):
        args = json.loads(tool_call["arguments"])
        self.replies.append(args["payload"])
        return {"type": "function_call_output", "call_id": tool_call["call_id"],
                "output": json.dumps({"message_id": f"r{len(self.replies)}", "error": None})}


class FakeSuperLinkGrid:
    """SuperLink-side grid. On push, runs `node_handler(agent, grid_msg)` synchronously per node."""

    def __init__(self, nodes: list[dict], node_handler=None, silent_nodes: set[str] = frozenset()):
        self.nodes = nodes
        self.node_handler = node_handler
        self.silent_nodes = set(silent_nodes)
        self.replies: dict[str, dict] = {}
        self.pushed: list[dict] = []
        self._ids = itertools.count(1)

    def tools(self):
        return [{"name": n} for n in ("get_nodes", "push_messages", "pull_messages")]

    def call(self, tool_call):
        name = tool_call["name"]
        args = json.loads(tool_call["arguments"])
        if name == "get_nodes":
            out = {"nodes": self.nodes, "num_available": len(self.nodes)}
        elif name == "push_messages":
            results = []
            for m in args["messages"]:
                mid = f"m{next(self._ids)}"
                self.pushed.append({**m, "message_id": mid})
                results.append({"message_id": mid, "error": None})
                if m["dst_node_id"] in self.silent_nodes or self.node_handler is None:
                    continue
                node_grid = NodeGrid()
                prompt = json.dumps({"message_id": mid, "src_node_id": "1", "payload": m["payload"]})
                self.node_handler(LocalAgent(prompt, grid=node_grid), json.loads(prompt))
                assert len(node_grid.replies) == 1, "node must reply exactly once"
                self.replies[mid] = {"message_id": f"reply-{mid}", "reply_to_message_id": mid,
                                     "src_node_id": m["dst_node_id"], "payload": node_grid.replies[0], "error": None}
            out = {"results": results}
        elif name == "pull_messages":
            got = [self.replies[i] for i in args["message_ids"] if i in self.replies]
            out = {"messages": got, "pending_message_ids": [i for i in args["message_ids"] if i not in self.replies]}
        else:
            raise ValueError(name)
        return {"type": "function_call_output", "call_id": tool_call["call_id"], "output": json.dumps(out)}
