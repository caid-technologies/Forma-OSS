"""Reusable Forma core package and public SDK entry point."""

from typing import TYPE_CHECKING, Any

from forma_core._version import __version__

if TYPE_CHECKING:
    from forma_core.client import FormaClient as FormaClient


def __getattr__(name: str) -> Any:
    if name == "FormaClient":
        from forma_core.client import FormaClient

        return FormaClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["FormaClient", "__version__"]
