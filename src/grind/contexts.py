"""Working contexts: a named, switchable narrowing of one source.

A context lives in the config file as ``[contexts.<name>]``. It names a
source and overrides that source's scope (which org, repos or projects, and
whether you see only your own tickets) without touching the source's
credentials. One context can be active at a time; which one is kept in the XDG
state directory, so switching never rewrites the config file.

Precedence, highest first: command flags, then the active context, then the
source's own config.
"""

from dataclasses import dataclass, field
from pathlib import Path

from .fsutil import atomic_write_text
from .logger import logger
from .xdg import get_state_dir

__all__ = [
    "CONTEXT_KEYS",
    "Context",
    "ContextError",
    "SCOPE_KEYS",
    "active_context_file",
    "apply_context",
    "load_contexts",
    "read_active_context",
    "write_active_context",
]

#: Keys that choose *where* a source looks. A context that sets any of them
#: replaces all of the source's own, so the source's ``repo`` can never
#: out-rank the context's ``org`` just by being more specific.
SCOPE_KEYS = ("org", "repo", "repos", "project", "projects")

#: Every key a context may set. Anything else, credentials above all, is
#: refused: a context narrows a source, it never redefines one.
CONTEXT_KEYS = frozenset({"source", "jql", "mine", *SCOPE_KEYS})

_ACTIVE_FILENAME = "context"


class ContextError(ValueError):
    """A context is defined or chosen wrongly. The message is shown as-is."""


@dataclass(frozen=True)
class Context:
    """One ``[contexts.<name>]`` table: a source and what to override on it."""

    name: str
    source: str
    #: The keys the context sets, other than ``source``.
    overrides: dict = field(default_factory=dict)

    def describe(self) -> str:
        """A one-line summary, e.g. ``oss: repos mrsixw/grind; yours``."""
        parts = []
        for key in (*SCOPE_KEYS, "jql"):
            value = self.overrides.get(key)
            if value:
                shown = ", ".join(value) if isinstance(value, list) else str(value)
                parts.append(f"{key} {shown}")
        if "mine" in self.overrides:
            parts.append("yours" if self.overrides["mine"] else "everyone's")
        return f"{self.source}: {'; '.join(parts) or 'the source as configured'}"


def load_contexts(cfg: dict) -> dict[str, Context]:
    """Parse every ``[contexts.<name>]`` table in *cfg*.

    Checks only what can be checked without the sources: the shape, the keys,
    and that ``source`` is named. Whether that source exists, and whether its
    provider takes the keys, is checked when the context is applied.
    """
    tables = cfg.get("contexts", {})
    if not isinstance(tables, dict):
        raise ContextError("'contexts' in the config must be a table of tables.")
    contexts = {}
    for name, table in tables.items():
        if not isinstance(table, dict):
            raise ContextError(f"Context '{name}' must be a table.")
        unknown = sorted(set(table) - CONTEXT_KEYS)
        if unknown:
            raise ContextError(
                f"Context '{name}' cannot set '{unknown[0]}'. A context takes "
                f"only: {', '.join(sorted(CONTEXT_KEYS))}."
            )
        source = table.get("source")
        if not isinstance(source, str) or not source:
            raise ContextError(
                f"Context '{name}' needs a source, e.g. source = \"oss\"."
            )
        if "mine" in table and not isinstance(table["mine"], bool):
            raise ContextError(
                f"Context '{name}': mine must be true or false, not '{table['mine']}'."
            )
        overrides = {key: value for key, value in table.items() if key != "source"}
        contexts[name] = Context(name=name, source=source, overrides=overrides)
    return contexts


def apply_context(context: Context, source_config: dict, scope_keys) -> dict:
    """Return *source_config* with *context*'s overrides laid over it.

    *scope_keys* are the keys the source's provider understands. A context
    setting a key outside them is an error rather than silently doing
    nothing. ``mine`` is understood by every source.
    """
    accepted = {*scope_keys, "mine"}
    refused = sorted(set(context.overrides) - accepted)
    if refused:
        takes = ", ".join(sorted(accepted))
        raise ContextError(
            f"Context '{context.name}' sets '{refused[0]}', which source "
            f"'{context.source}' does not take. It takes: {takes}."
        )
    merged = dict(source_config)
    if any(key in context.overrides for key in SCOPE_KEYS):
        for key in SCOPE_KEYS:
            merged.pop(key, None)
    merged.update(context.overrides)
    return merged


def active_context_file(state_dir: Path | None = None) -> Path:
    """Where the active context's name is kept."""
    return (state_dir or get_state_dir()) / _ACTIVE_FILENAME


def read_active_context(state_dir: Path | None = None) -> str | None:
    """Return the stored active context's name, or None when there is none.

    An unreadable file counts as none: losing the choice is a nuisance, but
    it must never stop a command from running.
    """
    path = active_context_file(state_dir)
    try:
        name = path.read_text().strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.debug("active_context_read_error error=%r", str(exc))
        return None
    return name or None


def write_active_context(name: str | None, state_dir: Path | None = None) -> None:
    """Store *name* as the active context, or clear it when *name* is None."""
    path = active_context_file(state_dir)
    if name is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, name + "\n")
