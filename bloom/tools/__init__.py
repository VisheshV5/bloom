"""Allowlisted local tools that specialists may use.

Each tool has an OpenAI Responses function schema and a Python implementation that
runs in-process (on the SuperLink or a SuperNode). Specs may only reference names in
TOOL_REGISTRY; the Forge reviewer enforces this.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from bloom.tools import calc, dates, sql, stats, text, units
from bloom.tools.sql import SCHEMA_DESCRIPTION


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]

    @property
    def schema(self) -> dict:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


_NUMS = {"type": "array", "items": {"type": "number"}}
_STR = {"type": "string"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}

_TOOLS = [
    Tool("run_sql", "Run one read-only, aggregating SQLite SELECT (GROUP BY or SUM/COUNT/AVG/MIN/MAX; no SELECT *; "
         "no ids except inside COUNT; max 200 rows) on the hospital database attached to this machine. " + SCHEMA_DESCRIPTION,
         _obj({"query": _STR}, ["query"]), lambda query: sql.run_sql(query)),
    Tool("describe", "Summary statistics (n, mean, median, sample stdev, min, max, sum) of a list of numbers.",
         _obj({"values": _NUMS}, ["values"]), stats.describe),
    Tool("percentile", "Percentile with linear interpolation; q in [0, 100].",
         _obj({"values": _NUMS, "q": _NUM}, ["values", "q"]), stats.percentile),
    Tool("ttest_welch", "Welch's two-sample t-test (two-sided). Returns t, df, p_value, and both means.",
         _obj({"a": _NUMS, "b": _NUMS}, ["a", "b"]), stats.ttest_welch),
    Tool("linregress", "Least-squares line y = slope*x + intercept, plus Pearson r.",
         _obj({"x": _NUMS, "y": _NUMS}, ["x", "y"]), stats.linregress),
    Tool("correlation", "Pearson correlation coefficient of x and y.",
         _obj({"x": _NUMS, "y": _NUMS}, ["x", "y"]), stats.correlation),
    Tool("add_days", "Add calendar days to an ISO date (YYYY-MM-DD).",
         _obj({"start": _STR, "days": _INT}, ["start", "days"]), dates.add_days),
    Tool("add_business_days", "Move N business days (Mon-Fri, no holidays) from an ISO date; start is not counted.",
         _obj({"start": _STR, "days": _INT}, ["start", "days"]), dates.add_business_days),
    Tool("business_days_between", "Count business days d with start < d <= end.",
         _obj({"start": _STR, "end": _STR}, ["start", "end"]), dates.business_days_between),
    Tool("business_days_in_range", "List business days d with start <= d <= end.",
         _obj({"start": _STR, "end": _STR}, ["start", "end"]), dates.business_days_in_range),
    Tool("days_between", "Calendar days from start to end (end - start).",
         _obj({"start": _STR, "end": _STR}, ["start", "end"]), dates.days_between),
    Tool("weekday", "Weekday name of an ISO date.", _obj({"date": _STR}, ["date"]),
         lambda date: dates.weekday(date)),
    Tool("convert_units", "Convert a value between units (mass g/kg/lb/oz, length mm/cm/m/km/in/ft/yd/mi, "
         "volume ml/l/floz/cup/gal, temperature c/f/k).",
         _obj({"value": _NUM, "from_unit": _STR, "to_unit": _STR}, ["value", "from_unit", "to_unit"]),
         units.convert),
    Tool("regex_findall", "Unique regex matches in order of first appearance (Python re syntax).",
         _obj({"pattern": _STR, "text": _STR}, ["pattern", "text"]), text.regex_findall),
    Tool("calculate", "Evaluate an arithmetic expression (+ - * / ** %, sqrt, log, exp, round, min, max).",
         _obj({"expression": _STR}, ["expression"]), calc.calculate),
]

TOOL_REGISTRY: dict[str, Tool] = {t.name: t for t in _TOOLS}


# Tools that only exist on a machine that has the resource attached.
_REQUIRES = {"run_sql": sql.available}


def available(name: str) -> bool:
    return name in TOOL_REGISTRY and _REQUIRES.get(name, lambda: True)()


def tool_schemas(names: list[str]) -> list[dict]:
    """Schemas for the requested tools that actually exist here (run_sql needs an attached DB)."""
    return [TOOL_REGISTRY[n].schema for n in names if available(n)]


def call_tool(name: str, arguments: Any) -> str:
    """Execute a tool and return a JSON string (errors are returned, never raised)."""
    try:
        if name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown tool {name!r}")
        if not available(name):
            raise RuntimeError(f"{name} is not available on this machine (no database attached)")
        args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be a JSON object")
        result = TOOL_REGISTRY[name].fn(**args)
        return json.dumps({"result": result}, default=str)
    except Exception as exc:  # noqa: BLE001 - errors go back to the model
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
