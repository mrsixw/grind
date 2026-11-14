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
"""

import os
import sys
from abc import ABC, abstractmethod
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path

import requests

from .constants import ENTRY_POINT_GROUP, HTTP_TIMEOUT_SECONDS, USER_AGENT
from .logger import logger
from .tickets import Comment, ListQuery, Ticket, TicketChanges, TicketDraft
from .xdg import get_data_dir

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


class ProviderError(Exception):
    """A provider could not do what was asked. The message is shown as-is."""


class Provider(ABC):
    """One ticket system. Instantiated once per configured source.

    Only reading is mandatory. The write operations default to a polite
    refusal, so a read-only plugin is a complete plugin.
    """

    #: The name used in ``provider = "..."``. Set by each subclass.
    name: str = ""

    def __init__(self, source: str, config: dict):
        self.source = source
        self.config = config
        #: How many upstream requests this source has made, for --debug-summary.
        self.request_count = 0

    # ── Required ───────────────────────────────────────────────────────────

    @abstractmethod
    def list_tickets(self, query: ListQuery) -> list[Ticket]:
        """Return tickets matching *query*, newest activity first."""

    @abstractmethod
    def get_ticket(self, key: str, *, comments: bool = False) -> Ticket:
        """Return one ticket, with its comments when *comments* is set."""

    # ── Optional ───────────────────────────────────────────────────────────

    def whoami(self) -> str:
        """Return a display name for the authenticated user."""
        raise self.unsupported("identifying the current user")

    def create_ticket(self, draft: TicketDraft) -> Ticket:
        raise self.unsupported("creating tickets")

    def update_ticket(self, key: str, changes: TicketChanges) -> Ticket:
        raise self.unsupported("editing tickets")

    def add_comment(self, key: str, body: str) -> Comment:
        raise self.unsupported("commenting")

    def assign(self, key: str, assignee: str | None) -> Ticket:
        """Assign to *assignee* (``tickets.ME`` for yourself), or unassign on None."""
        raise self.unsupported("assigning tickets")

    def transition(self, key: str, status: str) -> Ticket:
        """Move the ticket to *status*, in the provider's own vocabulary."""
        raise self.unsupported("moving tickets between statuses")

    # ── Helpers for subclasses ─────────────────────────────────────────────

    def unsupported(self, what: str) -> ProviderError:
        return ProviderError(
            f"The '{self.name}' provider (source '{self.source}') does not "
            f"support {what}."
        )

    def require(self, key: str) -> str:
        """Return config value *key*, or raise a ProviderError naming it."""
        value = self.config.get(key)
        if not value:
            raise ProviderError(
                f"Source '{self.source}' is missing '{key}' in its config "
                f"([sources.{self.source}])."
            )
        return str(value)


class HttpProvider(Provider):
    """Base class for anything with an HTTP API — which is nearly everything.

    Handles the parts every HTTP ticket system shares: the base URL, reading
    the token from the environment (never from the config file), timeouts,
    request counting, and turning transport and status failures into
    :class:`ProviderError` with a message a person can act on.

    Subclasses usually set :attr:`default_url` and :attr:`default_token_env`,
    and override :meth:`auth` when a bearer token is not what the API wants.
    """

    #: Used when the source config has no ``url``. Empty means url is required.
    default_url = ""
    #: Environment variables to try for the token when ``token-env`` is unset.
    default_token_env: tuple[str, ...] = ()

    def __init__(self, source: str, config: dict):
        super().__init__(source, config)
        self.base_url = str(config.get("url") or self.default_url).rstrip("/")
        if not self.base_url:
            raise ProviderError(
                f"Source '{source}' is missing 'url' in its config "
                f"([sources.{source}])."
            )
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def token(self) -> str:
        """Return the API token from the environment.

        ``token-env`` in the source config names the variable; otherwise the
        provider's defaults are tried in order. Tokens are never read from the
        config file, so a config is always safe to commit or paste.
        """
        configured = self.config.get("token-env")
        names = (str(configured),) if configured else self.default_token_env
        for name in names:
            value = os.environ.get(name)
            if value:
                return value
        wanted = " or ".join(names) if names else "a 'token-env' variable"
        raise ProviderError(
            f"No token for source '{self.source}'. Set {wanted} in your environment."
        )

    def auth(self):
        """Return the ``requests`` auth for a call. Default: a bearer token."""
        token = self.token()

        def bearer(request):
            request.headers["Authorization"] = f"Bearer {token}"
            return request

        return bearer

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make one authenticated call and return the successful response.

        *path* is joined onto the base URL unless it is already absolute,
        which lets pagination follow the links an API hands back.
        """
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        self.request_count += 1
        logger.debug("request source=%s %s %s", self.source, method, url)
        try:
            response = self.session.request(
                method,
                url,
                auth=self.auth(),
                timeout=HTTP_TIMEOUT_SECONDS,
                **kwargs,
            )
        except requests.exceptions.RequestException as exc:
            raise ProviderError(
                f"Could not reach source '{self.source}' at {self.base_url}: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise ProviderError(self.describe_failure(response))
        return response

    def describe_failure(self, response: requests.Response) -> str:
        """Turn an error response into a one-line explanation."""
        code = response.status_code
        prefix = f"Source '{self.source}' answered {code}"
        if code == 401:
            return f"{prefix}: the token was rejected. Check it has not expired."
        if code == 403:
            return f"{prefix}: the token is not allowed to do that."
        if code == 404:
            return f"{prefix}: not found (or not visible to this token)."
        detail = self.error_detail(response)
        return f"{prefix}: {detail}" if detail else f"{prefix}."

    def error_detail(self, response: requests.Response) -> str:
        """Extract the API's own error text. Override for richer messages."""
        return response.text.strip()[:200]


# ── Registry ───────────────────────────────────────────────────────────────

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
