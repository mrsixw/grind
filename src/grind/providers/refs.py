"""Ticket references: ``<source>:<key>``."""

from .base import Provider, ProviderError

__all__ = [
    "resolve_ref",
]


def resolve_ref(ref: str, sources: dict[str, Provider]) -> tuple[Provider, str]:
    """Split a ticket reference into its provider and the provider's key.

    ``work:PROJ-1`` names the source explicitly. With exactly one source
    configured the prefix may be dropped.
    """
    prefix, sep, rest = ref.partition(":")
    if sep and prefix in sources and rest:
        return sources[prefix], rest
    if len(sources) == 1:
        return next(iter(sources.values())), ref
    names = ", ".join(sources) or "none configured"
    raise ProviderError(
        f"Which source is '{ref}' from? Write it as <source>:<key>. Sources: {names}."
    )
