"""The GitHub Issues provider.

Keys are ``owner/repo#123``. With ``repo`` set on the source, ``#123`` or a
bare ``123`` is enough.
"""

import re

import requests

from .providers import HttpProvider, ProviderError, register_builtin
from .tickets import ME, Comment, ListQuery, Ticket, TicketChanges, TicketDraft

__all__ = [
    "GitHubProvider",
]

_KEY = re.compile(r"^(?:(?P<repo>[\w.-]+/[\w.-]+))?#?(?P<number>\d+)$")

#: What ``move`` accepts, mapped to the issue's state and state_reason.
_TRANSITIONS = {
    "open": ("open", None),
    "reopen": ("open", "reopened"),
    "reopened": ("open", "reopened"),
    "closed": ("closed", "completed"),
    "close": ("closed", "completed"),
    "done": ("closed", "completed"),
    "completed": ("closed", "completed"),
    "not-planned": ("closed", "not_planned"),
    "wontfix": ("closed", "not_planned"),
}


@register_builtin
class GitHubProvider(HttpProvider):
    """GitHub Issues, on github.com or GitHub Enterprise (set ``url``)."""

    name = "github"
    default_url = "https://api.github.com"
    default_token_env = ("GH_TOKEN", "GITHUB_TOKEN")

    def __init__(self, source: str, config: dict):
        super().__init__(source, config)
        self.session.headers["Accept"] = "application/vnd.github+json"
        self.session.headers["X-GitHub-Api-Version"] = "2022-11-28"

    def error_detail(self, response: requests.Response) -> str:
        try:
            return str(response.json().get("message", ""))
        except (ValueError, AttributeError):
            return super().error_detail(response)

    # ── Keys ───────────────────────────────────────────────────────────────

    def _split(self, key: str) -> tuple[str, int]:
        match = _KEY.match(key.strip())
        repo = (match and match["repo"]) or self.config.get("repo")
        if not match or not repo:
            raise ProviderError(
                f"'{key}' is not a GitHub issue. Use owner/repo#123, or set "
                f"'repo' on source '{self.source}' and use #123."
            )
        return str(repo), int(match["number"])

    def _repo(self, container: str) -> str:
        repo = container or self.config.get("repo")
        if not repo:
            raise ProviderError(
                f"Which repository? Pass --in owner/repo, or set 'repo' on "
                f"source '{self.source}'."
            )
        return str(repo)

    def _ticket(self, issue: dict, comments: tuple[Comment, ...] = ()) -> Ticket:
        # Search results carry no "repository" object, only its API URL.
        repo = issue["repository_url"].rsplit("/repos/", 1)[-1]
        assignees = [a["login"] for a in issue.get("assignees") or []]
        status = issue["state"]
        if status == "closed" and issue.get("state_reason") == "not_planned":
            status = "not planned"
        return Ticket(
            source=self.source,
            key=f"{repo}#{issue['number']}",
            title=issue["title"],
            status=status,
            is_open=issue["state"] == "open",
            type=(issue.get("type") or {}).get("name", "") or "issue",
            assignee=", ".join(assignees),
            reporter=(issue.get("user") or {}).get("login", ""),
            labels=tuple(label["name"] for label in issue.get("labels") or []),
            url=issue.get("html_url", ""),
            created=issue.get("created_at", ""),
            updated=issue.get("updated_at", ""),
            body=issue.get("body") or "",
            comments=comments,
        )

    # ── Reading ────────────────────────────────────────────────────────────

    def whoami(self) -> str:
        return self.request("GET", "/user").json()["login"]

    def list_tickets(self, query: ListQuery) -> list[Ticket]:
        repo = query.container or self.config.get("repo")
        if not repo and not query.mine:
            raise ProviderError(
                f"Listing everyone's issues needs a repository: pass --in "
                f"owner/repo, or set 'repo' on source '{self.source}'."
            )
        terms = ["is:issue"]
        if repo:
            terms.append(f"repo:{repo}")
        if query.mine:
            terms.append("assignee:@me")
        if query.state != "all":
            terms.append(f"state:{query.state}")
        if query.text:
            terms.append(query.text)

        tickets: list[Ticket] = []
        page = 1
        while len(tickets) < query.limit:
            per_page = min(100, query.limit - len(tickets))
            items = self.request(
                "GET",
                "/search/issues",
                params={
                    "q": " ".join(terms),
                    "sort": "updated",
                    "order": "desc",
                    "per_page": per_page,
                    "page": page,
                },
            ).json()["items"]
            tickets += [self._ticket(item) for item in items]
            if len(items) < per_page:
                break
            page += 1
        return tickets[: query.limit]

    def get_ticket(self, key: str, *, comments: bool = False) -> Ticket:
        repo, number = self._split(key)
        path = f"/repos/{repo}/issues/{number}"
        issue = self.request("GET", path).json()
        if "pull_request" in issue:
            raise ProviderError(f"{repo}#{number} is a pull request, not an issue.")
        found: tuple[Comment, ...] = ()
        if comments:
            raw = self.request(
                "GET", f"{path}/comments", params={"per_page": 100}
            ).json()
            found = tuple(
                Comment(
                    author=(c.get("user") or {}).get("login", ""),
                    body=c.get("body") or "",
                    created=c.get("created_at", ""),
                )
                for c in raw
            )
        return self._ticket(issue, found)

    # ── Writing ────────────────────────────────────────────────────────────

    def _login(self, assignee: str) -> str:
        return self.whoami() if assignee == ME else assignee

    def create_ticket(self, draft: TicketDraft) -> Ticket:
        if draft.type:
            raise ProviderError(
                "GitHub issues have no --type here; use --label instead."
            )
        payload: dict = {"title": draft.title, "body": draft.body}
        if draft.labels:
            payload["labels"] = list(draft.labels)
        if draft.assignee:
            payload["assignees"] = [self._login(draft.assignee)]
        repo = self._repo(draft.container)
        issue = self.request("POST", f"/repos/{repo}/issues", json=payload).json()
        return self._ticket(issue)

    def _patch(self, key: str, payload: dict) -> Ticket:
        repo, number = self._split(key)
        issue = self.request(
            "PATCH", f"/repos/{repo}/issues/{number}", json=payload
        ).json()
        return self._ticket(issue)

    def update_ticket(self, key: str, changes: TicketChanges) -> Ticket:
        payload: dict = {}
        if changes.title is not None:
            payload["title"] = changes.title
        if changes.body is not None:
            payload["body"] = changes.body
        if changes.add_labels or changes.remove_labels:
            # The API replaces the whole label set, so start from what is there.
            current = self.get_ticket(key).labels
            kept = [name for name in current if name not in changes.remove_labels]
            added = [name for name in changes.add_labels if name not in kept]
            payload["labels"] = kept + added
        return self._patch(key, payload)

    def add_comment(self, key: str, body: str) -> Comment:
        repo, number = self._split(key)
        created = self.request(
            "POST", f"/repos/{repo}/issues/{number}/comments", json={"body": body}
        ).json()
        return Comment(
            author=(created.get("user") or {}).get("login", ""),
            body=created.get("body") or "",
            created=created.get("created_at", ""),
        )

    def assign(self, key: str, assignee: str | None) -> Ticket:
        assignees = [self._login(assignee)] if assignee else []
        return self._patch(key, {"assignees": assignees})

    def transition(self, key: str, status: str) -> Ticket:
        wanted = _TRANSITIONS.get(status.strip().lower().replace(" ", "-"))
        if wanted is None:
            raise ProviderError(
                f"GitHub issues cannot move to '{status}'. "
                "Choose from: open, closed, not-planned."
            )
        state, reason = wanted
        payload = {"state": state}
        if reason:
            payload["state_reason"] = reason
        return self._patch(key, payload)
