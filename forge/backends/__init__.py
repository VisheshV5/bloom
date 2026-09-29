"""LLM backends for the Forge and the evaluator."""

from __future__ import annotations


def make_backend(name: str, bus, **kwargs):
    if name == "mock":
        from forge.backends.mock import MockBackend
        return MockBackend(bus, **kwargs)
    if name == "supergrid":
        from forge.backends.supergrid import SuperGridBackend
        return SuperGridBackend(bus, **kwargs)
    if name == "nebius":
        from forge.backends.nebius import NebiusBackend
        return NebiusBackend(bus, **kwargs)
    raise ValueError(f"unknown backend {name!r}")
