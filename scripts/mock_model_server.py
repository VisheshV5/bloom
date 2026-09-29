"""A tiny fake Open Responses endpoint for testing Bloom on a LOCAL Flower SuperLink.

  uv run python scripts/mock_model_server.py --port 8080
  export FLWR_MODEL_API_ENDPOINT=http://127.0.0.1:8080/v1/responses

It answers deterministically (plans, specs, a run_sql tool call, `FINAL: ...`) and logs
every request to runs/mock_model_requests.jsonl, so we can see exactly what Flower's
runtime forwards (e.g. whether `instructions` arrives). Non-streaming only.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / "runs" / "mock_model_requests.jsonl"

PLAN = {"steps": [
    {"step_id": "s1", "specialist": "sql-analyst", "instruction": "Count the stores.", "depends_on": []},
    {"step_id": "s2", "specialist": "generalist", "instruction": "Summarize for the CEO.", "depends_on": ["s1"]}],
    "missing_capabilities": []}
SPEC = {"slug": "mock-analyst", "category": "sql", "purpose": "Mock spec from the fake model.",
        "instructions": "Use run_sql. End with `FINAL: <answer>`.", "model": "openai/gpt-5.6-sol",
        "tools": ["run_sql"], "capabilities": ["sql"], "output_format": "FINAL line", "version": 1}


def _text(t: str) -> dict:
    return {"type": "message", "id": f"msg_{uuid.uuid4().hex[:8]}", "status": "completed", "role": "assistant",
            "content": [{"type": "output_text", "text": t, "annotations": []}]}


def _call(name: str, args: dict) -> dict:
    return {"type": "function_call", "id": f"fc_{uuid.uuid4().hex[:8]}", "call_id": f"call_{uuid.uuid4().hex[:8]}",
            "name": name, "arguments": json.dumps(args), "status": "completed"}


def respond(req: dict) -> list[dict]:
    instructions = str(req.get("instructions") or "")
    items = req.get("input") if isinstance(req.get("input"), list) else []
    text_in = json.dumps(items) + instructions
    tools = [t.get("name") for t in req.get("tools") or []]
    tool_outputs = [i for i in items if isinstance(i, dict) and i.get("type") == "function_call_output"]
    if "planner of Bloom" in instructions:
        return [_text(json.dumps(PLAN))]
    if "Architect in Bloom" in instructions:
        return [_text(json.dumps(SPEC))]
    if "Builder in Bloom" in instructions:
        return [_text(json.dumps({"instructions": SPEC["instructions"], "examples": [],
                                  "postprocess_body": "    m = re.findall(r'FINAL:\\s*(.+)', text)\n    return m[-1] if m else None"}))]
    if "run_sql" in tools and not tool_outputs:
        return [_call("run_sql", {"query": "SELECT COUNT(*) FROM stores"})]
    if tool_outputs:
        out = json.loads(tool_outputs[-1]["output"])
        rows = (out.get("result") or {}).get("rows")
        return [_text(f"The query returned {rows}.\nFINAL: {rows[0][0] if rows else 'none'}")]
    tag = "instructions=yes" if instructions else "instructions=no"
    return [_text(f"Mock answer ({tag}; saw {len(text_in)} chars).\nFINAL: 42")]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
        try:
            req = json.loads(body or b"{}")
        except ValueError:
            req = {}
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps({"ts": time.time(), "path": self.path, "request": req}) + "\n")
        if req.get("stream"):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": {"message": "mock server does not stream"}}')
            return
        resp = {
            "id": f"resp_{uuid.uuid4().hex[:10]}", "object": "response", "created_at": int(time.time()),
            "status": "completed", "model": req.get("model", "mock"), "output": respond(req),
            "parallel_tool_calls": True, "tool_choice": req.get("tool_choice", "auto"), "tools": req.get("tools", []),
            "error": None, "incomplete_details": None, "instructions": req.get("instructions"), "metadata": {},
            "temperature": 1.0, "top_p": 1.0, "text": {"format": {"type": "text"}},
            "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20,
                      "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    print(f"mock model server on http://127.0.0.1:{args.port}/v1/responses")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
