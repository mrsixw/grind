"""Pantry: an in-memory provider plugin for driving the CLI in tests.

It is installed the way a real plugin is, through a ``grind.providers`` entry
point, so the CLI finds it exactly as it would find one on disk. Every call is
recorded on the shelf, so a test can check what the CLI asked for as well as
what it printed.

Import ``pantry_fixture`` to get the ``pantry`` fixture, then stock the shelf
with tickets, point a source at ``provider = "pantry"``, and run the CLI.
"""

from dataclasses import replace
from importlib.metadata import EntryPoint

import pytest

from grind import providers as providers_mod
from grind.constants import ENTRY_POINT_GROUP
from grind.providers import Provider, ProviderError
from grind.tickets import ME, Comment, Ticket

#: The statuses ``move`` accepts, and whether a ticket in each is open.
STATUSES = {"open": True, "closed": False}

#: Where the entry point says the provider lives.
ENTRY_POINT_VALUE = "tests.pantry:Pantry"


class Shelf:
    """What the pantry holds, and a log of every call made to it."""

    def __init__(self):
        self.stock: dict[str, dict[str, Ticket]] = {}
        #: ``(source, operation, argument)`` for every call, in order.
        self.calls: list[tuple[str, str, object]] = []
        #: Source name to the error message every call on it raises.
        self.failures: dict[str, str] = {}
        #: Who the source's credentials belong to.
        self.me = "ada"

    def add(self, *tickets: Ticket) -> None:
        for ticket in tickets:
            self.stock.setdefault(ticket.source, {})[ticket.key] = ticket

    def made(self, operation: str, source: str | None = None) -> list:
        """The arguments of every *operation* call, optionally on one source."""
        return [
            arg
            for src, op, arg in self.calls
            if op == operation and source in (None, src)
        ]


class Pantry(Provider):
    """Keeps tickets in memory. Supports every operation."""

    name = "pantry"
    shelf: Shelf = Shelf()

    def _call(self, operation: str, arg=None) -> None:
        self.request_count += 1
        self.shelf.calls.append((self.source, operation, arg))
        if self.source in self.shelf.failures:
            raise ProviderError(self.shelf.failures[self.source])

    def _get(self, key: str) -> Ticket:
        try:
            return self.shelf.stock[self.source][key]
        except KeyError:
            raise ProviderError(
                f"Source '{self.source}' has no ticket {key}."
            ) from None

    def _put(self, ticket: Ticket) -> Ticket:
        self.shelf.add(ticket)
        return ticket

    def whoami(self) -> str:
        self._call("whoami")
        return self.shelf.me

    def list_tickets(self, query):
        self._call("list", query)
        return list(self.shelf.stock.get(self.source, {}).values())[: query.limit]

    def get_ticket(self, key, *, comments=False):
        self._call("get", key)
        ticket = self._get(key)
        return ticket if comments else replace(ticket, comments=())

    def create_ticket(self, draft):
        self._call("create", draft)
        key = str(len(self.shelf.stock.get(self.source, {})) + 1)
        return self._put(
            Ticket(
                source=self.source,
                key=key,
                title=draft.title,
                status="open",
                type=draft.type,
                body=draft.body,
                labels=draft.labels,
                url=f"https://pantry.example/{self.source}/{key}",
            )
        )

    def update_ticket(self, key, changes):
        self._call("update", (key, changes))
        ticket = self._get(key)
        removed = changes.remove_labels
        kept = tuple(name for name in ticket.labels if name not in removed)
        added = tuple(name for name in changes.add_labels if name not in kept)
        return self._put(
            replace(
                ticket,
                title=ticket.title if changes.title is None else changes.title,
                body=ticket.body if changes.body is None else changes.body,
                labels=kept + added,
            )
        )

    def add_comment(self, key, body):
        self._call("comment", (key, body))
        ticket = self._get(key)
        comment = Comment(author=self.shelf.me, body=body)
        self._put(replace(ticket, comments=(*ticket.comments, comment)))
        return comment

    def assign(self, key, assignee):
        self._call("assign", (key, assignee))
        who = self.shelf.me if assignee == ME else (assignee or "")
        return self._put(replace(self._get(key), assignee=who))

    def transition(self, key, status):
        self._call("move", (key, status))
        wanted = status.strip().lower()
        if wanted not in STATUSES:
            raise ProviderError(
                f"{key} cannot move to '{status}'. Available: {', '.join(STATUSES)}."
            )
        return self._put(
            replace(self._get(key), status=wanted, is_open=STATUSES[wanted])
        )


@pytest.fixture(name="pantry")
def pantry_fixture(monkeypatch) -> Shelf:
    """Install the pantry plugin with an empty shelf, and return the shelf."""
    shelf = Shelf()
    monkeypatch.setattr(Pantry, "shelf", shelf)
    entry_point = EntryPoint(
        name=Pantry.name, value=ENTRY_POINT_VALUE, group=ENTRY_POINT_GROUP
    )
    monkeypatch.setattr(providers_mod, "entry_points", lambda group: [entry_point])
    return shelf
