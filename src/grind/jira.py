"""The JIRA provider: a stub for now.

It registers the provider name and where the token comes from, so a source
can already be configured and shows up in ``grind sources``. Every operation
raises a ProviderError saying it is a stub; the real API calls follow in
their own change.
"""

from .providers import HttpProvider, ProviderError, register_builtin
from .tickets import Comment, ListQuery, Ticket, TicketChanges, TicketDraft

__all__ = [
    "JiraProvider",
]


@register_builtin
class JiraProvider(HttpProvider):
    """JIRA Cloud, Server or Data Center. ``url`` is required."""

    name = "jira"
    default_token_env = ("JIRA_TOKEN", "JIRA_API_TOKEN")

    def _not_yet(self, what: str) -> ProviderError:
        return ProviderError(
            f"The '{self.name}' provider (source '{self.source}') cannot do "
            f"{what} yet: it is a stub."
        )

    def whoami(self) -> str:
        raise self._not_yet("identifying the current user")

    def list_tickets(self, query: ListQuery) -> list[Ticket]:
        raise self._not_yet("listing tickets")

    def get_ticket(self, key: str, *, comments: bool = False) -> Ticket:
        raise self._not_yet("showing tickets")

    def create_ticket(self, draft: TicketDraft) -> Ticket:
        raise self._not_yet("creating tickets")

    def update_ticket(self, key: str, changes: TicketChanges) -> Ticket:
        raise self._not_yet("editing tickets")

    def add_comment(self, key: str, body: str) -> Comment:
        raise self._not_yet("commenting")

    def assign(self, key: str, assignee: str | None) -> Ticket:
        raise self._not_yet("assigning tickets")

    def transition(self, key: str, status: str) -> Ticket:
        raise self._not_yet("moving tickets between statuses")
