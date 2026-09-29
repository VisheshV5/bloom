"""Human approval gate: show spec + diff + review, wait for an explicit y."""

from __future__ import annotations

import difflib
import json
import sys


def unified_diff(path: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        f"a/{path}" if old else "/dev/null", f"b/{path}",
    ))


class TerminalApprover:
    """Asks at the terminal. `auto=True` is only allowed with the mock backend."""

    def __init__(self, auto: bool = False, backend_name: str = "mock", input_fn=input, out=sys.stdout):
        if auto and backend_name != "mock":
            raise ValueError("--auto-approve is only allowed with the mock backend")
        self.auto = auto
        self.input_fn = input_fn
        self.out = out

    def _print(self, text: str = "") -> None:
        print(text, file=self.out)

    def show(self, spec: dict, diffs: list[str], review: dict, commands: list[str]) -> None:
        bar = "=" * 72
        self._print(f"\n{bar}\nFORGE: new specialist ready for approval: {spec['slug']}\n{bar}")
        self._print(json.dumps({k: spec[k] for k in spec if k != "instructions"}, indent=2))
        self._print(f"\nInstructions:\n  {spec['instructions']}\n")
        tests = review.get("tests") or {}
        self._print(f"Review: static={'OK' if not review.get('static') else review['static']}  "
                    f"contract={'OK' if not review.get('contract') else review['contract']}  "
                    f"build={'OK' if (review.get('build') or {}).get('ok') else review.get('build')}  "
                    f"tests={tests.get('passed')}/{tests.get('total')}  attempts={review.get('attempts')}")
        self._print("\nDiff:")
        for d in diffs:
            self._print(d)
        if commands:
            self._print("Side effects after approval:")
            for c in commands:
                self._print(f"  $ {c}")

    def confirm(self, question: str) -> bool:
        if self.auto:
            self._print(f"{question} [y/N] y   (auto-approved: mock backend)")
            return True
        try:
            answer = self.input_fn(f"{question} [y/N] ")
        except EOFError:
            return False
        return answer.strip() in {"y", "Y"}
