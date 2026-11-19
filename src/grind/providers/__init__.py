"""The provider plugin interface, and the registry that finds providers.

A *provider* teaches grind to talk to one kind of ticket system. A *source* is
one configured instance of a provider — ``[sources.work]`` in the config file.

Writing a plugin
----------------
Subclass :class:`HttpProvider` (or :class:`Provider`, for something that is
not HTTP), implement ``list_tickets`` and ``get_ticket``, override whichever
write operations the system supports, and register the class under the
``grind.providers`` entry-point group::

    [project.entry-points."grind.providers"]
    trello = "grind_trello:TrelloProvider"

Anything importable works. Because grind ships as a self-contained zipapp,
packages installed into the plugin directory (see :func:`plugin_dir`) are put
on ``sys.path`` before discovery, so ``pip install --target`` is enough.

Layout
------
Everything a plugin needs is importable from ``grind.providers``. Inside,
the package is split by job:

- ``base``: :class:`Provider` and :class:`ProviderError`
- ``http``: :class:`HttpProvider`
- ``registry``: built-ins, entry-point plugins and building sources
- ``refs``: parsing ``<source>:<key>`` references
"""

from .base import Provider, ProviderError
from .http import HttpProvider
from .refs import resolve_ref
from .registry import available_providers, build_sources, plugin_dir, register_builtin

__all__ = [
    "HttpProvider",
    "Provider",
    "ProviderError",
    "available_providers",
    "build_sources",
    "plugin_dir",
    "register_builtin",
    "resolve_ref",
]
