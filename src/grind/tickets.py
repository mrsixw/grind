"""The ticket model every provider speaks.

A provider's whole job is to translate its system's vocabulary into these few
dataclasses and back. Nothing here knows about HTTP, JIRA or GitHub, so the
CLI can render and edit tickets without caring where they were brewed.
"""

from dataclasses import asdict, dataclass

__all__ = [
    "Comment",
    "ListQuery",
    "ME",
    "STATES",
    "Ticket",
    "TicketChanges",
    "TicketDraft",
]

#: Assignee sentinel meaning "whoever the source's credentials belong to".
#:
#: ``grind assign REF`` with no user, and ``create --assignee @me``, pass this
#: rather than a name, because "me" is spelled differently on every system and
#: only the provider knows how to look it up: GitHub uses the token's login,
#: JIRA the account ID (Cloud) or username (Server) from ``/myself``. A plugin
#: that supports ``assign`` should handle it the same way.
ME = "@me"

#: The states ``ListQuery.state`` accepts.
STATES = ("open", "closed", "all")


@dataclass(frozen=True)
class Comment:
    """One comment on a ticket."""

    author: str
    body: str
    created: str = ""


@dataclass(frozen=True)
class Ticket:
    """A ticket, normalised across providers.

    *key* is the provider's own identifier (``PROJ-123``, ``owner/repo#7``).
    *status* is the provider's wording; *is_open* is the one thing every
    system agrees on.
    """

    source: str
    key: str
    title: str
    status: str
    is_open: bool = True
    type: str = ""
    assignee: str = ""
    reporter: str = ""
    labels: tuple[str, ...] = ()
    url: str = ""
    created: str = ""
    updated: str = ""
    body: str = ""
    comments: tuple[Comment, ...] = ()

    @property
    def ref(self) -> str:
        """The reference a user types to address this ticket."""
        return f"{self.source}:{self.key}"

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict, including the computed ``ref``."""
        data = asdict(self)
        data["labels"] = list(self.labels)
        data["ref"] = self.ref
        return data


@dataclass(frozen=True)
class ListQuery:
    """What ``list`` asks of a provider."""

    mine: bool = True
    state: str = "open"
    text: str = ""
    limit: int = 50
    #: Projects, repos or whatever the provider files tickets under, ORed
    #: together. Empty means the source's configured scope, or everything.
    containers: tuple[str, ...] = ()


@dataclass(frozen=True)
class TicketDraft:
    """A ticket to create."""

    title: str
    body: str = ""
    type: str = ""
    labels: tuple[str, ...] = ()
    assignee: str = ""
    container: str = ""


@dataclass(frozen=True)
class TicketChanges:
    """Edits to an existing ticket. ``None`` means "leave it alone"."""

    title: str | None = None
    body: str | None = None
    add_labels: tuple[str, ...] = ()
    remove_labels: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return (
            self.title is None
            and self.body is None
            and not self.add_labels
            and not self.remove_labels
        )
