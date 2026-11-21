"""Finding providers: the built-ins, and plugins from entry points.

A source's ``provider = "..."`` is looked up here, first among the providers
that ship with grind and then among installed plugins.
"""

import os
import sys
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path

from ..constants import ENTRY_POINT_GROUP
from ..xdg import get_data_dir
from .base import Provider, ProviderError

__all__ = [
    "available_providers",
    "build_sources",
    "plugin_dir",
    "register_builtin",
]

_BUILTINS: dict[str, type[Provider]] = {}


def register_builtin(cls: type[Provider]) -> type[Provider]:
    """Class decorator registering a provider that ships inside grind."""
    _BUILTINS[cls.name] = cls
    return cls


def plugin_dir() -> Path:
    """Directory whose contents are importable as provider plugins.

    ``pip install --target "$(grind sources --plugin-dir)" grind-something``
    """
    return get_data_dir() / "plugins"


def _plugin_entry_points() -> dict[str, EntryPoint]:
    directory = str(plugin_dir())
    if os.path.isdir(directory) and directory not in sys.path:
        sys.path.append(directory)
    return {ep.name: ep for ep in entry_points(group=ENTRY_POINT_GROUP)}


def available_providers() -> dict[str, str]:
    """Map every known provider name to where it comes from."""
    found = {name: "built-in" for name in _BUILTINS}
    for name, ep in _plugin_entry_points().items():
        # A plugin cannot shadow a built-in: a config that says "github" must
        # mean the same thing on every machine.
        found.setdefault(name, f"plugin ({ep.value})")
    return dict(sorted(found.items()))


def _load_provider(name: str) -> type[Provider]:
    if name in _BUILTINS:
        return _BUILTINS[name]
    ep = _plugin_entry_points().get(name)
    if ep is None:
        known = ", ".join(available_providers()) or "none"
        raise ProviderError(f"Unknown provider '{name}'. Available: {known}.")
    try:
        cls = ep.load()
    except (ImportError, AttributeError) as exc:
        raise ProviderError(f"Provider plugin '{name}' failed to load: {exc}") from exc
    if not (isinstance(cls, type) and issubclass(cls, Provider)):
        raise ProviderError(
            f"Provider plugin '{name}' ({ep.value}) is not a grind Provider subclass."
        )
    return cls


def build_sources(cfg: dict) -> dict[str, Provider]:
    """Instantiate a provider for every ``[sources.<name>]`` table in *cfg*."""
    tables = cfg.get("sources", {})
    if not isinstance(tables, dict):
        raise ProviderError("'sources' in the config must be a table of tables.")
    sources: dict[str, Provider] = {}
    for name, table in tables.items():
        if ":" in name:
            raise ProviderError(f"Source name '{name}' must not contain ':'.")
        if not isinstance(table, dict) or not table.get("provider"):
            raise ProviderError(
                f"Source '{name}' needs a 'provider' key, e.g. provider = \"github\"."
            )
        sources[name] = _load_provider(str(table["provider"]))(name, table)
    return sources
