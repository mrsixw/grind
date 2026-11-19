"""The provider interface every ticket system implements.

:class:`Provider` is the one class a plugin must subclass (directly, or through
:class:`~grind.providers.HttpProvider`). :class:`ProviderError` is how any
provider reports a problem the user can act on.
"""

from abc import ABC, abstractmethod

from ..tickets import Comment, ListQuery, Ticket, TicketChanges, TicketDraft

__all__ = [
    "Provider",
    "ProviderError",
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
