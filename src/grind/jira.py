"""The JIRA provider.

Speaks REST v3 to JIRA Cloud by default (``user`` + API token, HTTP Basic) and
REST v2 to Server / Data Center when the source sets ``api-version = 2``
(personal access token, bearer). Keys are JIRA's own: ``PROJ-123``.
"""

import requests

from .providers import HttpProvider, ProviderError, register_builtin
from .tickets import ME, Comment, ListQuery, Ticket, TicketChanges, TicketDraft

__all__ = [
    "JiraProvider",
    "adf_to_text",
    "text_to_adf",
]

_FIELDS = (
    "summary,status,issuetype,assignee,reporter,labels,created,updated,description"
)


def text_to_adf(text: str) -> dict:
    """Wrap plain text in Atlassian Document Format, one paragraph per block.

    REST v3 rejects a bare string for descriptions and comments.
    """
    paragraphs = []
    for block in text.split("\n\n"):
        content = []
        for i, line in enumerate(block.split("\n")):
            if i:
                content.append({"type": "hardBreak"})
            if line:
                content.append({"type": "text", "text": line})
        paragraphs.append({"type": "paragraph", "content": content})
    return {"type": "doc", "version": 1, "content": paragraphs}


def adf_to_text(node) -> str:
    """Flatten Atlassian Document Format to plain text.

    Lossy by design: marks, tables and media collapse to their text. A string
    (REST v2) or None passes straight through.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    kind = node.get("type")
    if kind == "text":
        return node.get("text", "")
    if kind == "hardBreak":
        return "\n"
    if kind == "mention":
        return node.get("attrs", {}).get("text", "")
    children = [adf_to_text(child) for child in node.get("content", [])]
    if kind in ("doc", "bulletList", "orderedList"):
        return (
            "\n\n".join(c for c in children if c)
            if kind == "doc"
            else "\n".join(children)
        )
    if kind == "listItem":
        return "- " + "".join(children)
    return "".join(children)


def _jql_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


@register_builtin
class JiraProvider(HttpProvider):
    """JIRA Cloud, Server or Data Center."""

    name = "jira"
    default_token_env = ("JIRA_TOKEN", "JIRA_API_TOKEN")

    def __init__(self, source: str, config: dict):
        super().__init__(source, config)
        version = str(config.get("api-version", "3"))
        if version not in ("2", "3"):
            raise ProviderError(
                f"Source '{source}': api-version must be 2 or 3, not '{version}'."
            )
        self.cloud = version == "3"
        self.api = f"/rest/api/{version}"
        self.session.headers["Accept"] = "application/json"

    def auth(self):
        user = self.config.get("user")
        if user:
            return (str(user), self.token())
        return super().auth()

    def error_detail(self, response: requests.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return super().error_detail(response)
        if not isinstance(data, dict):
            return ""
        messages = list(data.get("errorMessages") or [])
        messages += [f"{k}: {v}" for k, v in (data.get("errors") or {}).items()]
        return "; ".join(messages)

    # ── Translation ────────────────────────────────────────────────────────

    def _body(self, text: str):
        return text_to_adf(text) if self.cloud else text

    def _ticket(self, issue: dict, *, comments: bool = False) -> Ticket:
        fields = issue.get("fields") or {}
        status = fields.get("status") or {}
        found: tuple[Comment, ...] = ()
        if comments:
            found = tuple(
                self._comment(c)
                for c in (fields.get("comment") or {}).get("comments", [])
            )
        return Ticket(
            source=self.source,
            key=issue["key"],
            title=fields.get("summary", ""),
            status=status.get("name", ""),
            is_open=(status.get("statusCategory") or {}).get("key") != "done",
            type=(fields.get("issuetype") or {}).get("name", ""),
            assignee=(fields.get("assignee") or {}).get("displayName", ""),
            reporter=(fields.get("reporter") or {}).get("displayName", ""),
            labels=tuple(fields.get("labels") or []),
            url=f"{self.base_url}/browse/{issue['key']}",
            created=fields.get("created", ""),
            updated=fields.get("updated", ""),
            body=adf_to_text(fields.get("description")),
            comments=found,
        )

    @staticmethod
    def _comment(raw: dict) -> Comment:
        return Comment(
            author=(raw.get("author") or {}).get("displayName", ""),
            body=adf_to_text(raw.get("body")),
            created=raw.get("created", ""),
        )

    # ── Reading ────────────────────────────────────────────────────────────

    def whoami(self) -> str:
        return self.request("GET", f"{self.api}/myself").json()["displayName"]

    def _jql(self, query: ListQuery) -> str:
        clauses = []
        if len(query.containers) > 1:
            raise ProviderError(
                f"Source '{self.source}' is JIRA, which takes one --in project."
            )
        project = (query.containers or (None,))[0] or self.config.get("project")
        if project:
            clauses.append(f"project = {_jql_quote(str(project))}")
        if self.config.get("jql"):
            clauses.append(f"({self.config['jql']})")
        if query.mine:
            clauses.append("assignee = currentUser()")
        if query.state == "open":
            clauses.append("statusCategory != Done")
        elif query.state == "closed":
            clauses.append("statusCategory = Done")
        if query.text:
            clauses.append(f"text ~ {_jql_quote(query.text)}")
        return " AND ".join(clauses) + " ORDER BY updated DESC"

    def list_tickets(self, query: ListQuery) -> list[Ticket]:
        jql = self._jql(query)
        if jql.startswith(" ORDER"):
            # Cloud refuses unbounded searches; say so before it does.
            raise ProviderError(
                f"That would list every ticket on source '{self.source}'. "
                "Narrow it with --mine, --in PROJECT, --state or --query, or set "
                "'project' or 'jql' on the source."
            )
        tickets: list[Ticket] = []
        cursor: dict = {}
        while len(tickets) < query.limit:
            params = {
                "jql": jql,
                "fields": _FIELDS,
                "maxResults": min(100, query.limit - len(tickets)),
                **cursor,
            }
            # Cloud retired /search for the token-paginated /search/jql.
            path = f"{self.api}/search/jql" if self.cloud else f"{self.api}/search"
            page = self.request("GET", path, params=params).json()
            issues = page.get("issues", [])
            tickets += [self._ticket(issue) for issue in issues]
            if self.cloud:
                if not page.get("nextPageToken"):
                    break
                cursor = {"nextPageToken": page["nextPageToken"]}
            else:
                if not issues or len(tickets) >= page.get("total", 0):
                    break
                cursor = {"startAt": len(tickets)}
        return tickets[: query.limit]

    def get_ticket(self, key: str, *, comments: bool = False) -> Ticket:
        fields = _FIELDS + (",comment" if comments else "")
        issue = self.request(
            "GET", f"{self.api}/issue/{key}", params={"fields": fields}
        ).json()
        return self._ticket(issue, comments=comments)

    # ── Writing ────────────────────────────────────────────────────────────

    def _user_ref(self, assignee: str) -> dict:
        """Return the JSON JIRA wants for a user: accountId (Cloud) or name."""
        if assignee == ME:
            me = self.request("GET", f"{self.api}/myself").json()
            return (
                {"accountId": me["accountId"]} if self.cloud else {"name": me["name"]}
            )
        if not self.cloud:
            return {"name": assignee}
        matches = self.request(
            "GET", f"{self.api}/user/search", params={"query": assignee}
        ).json()
        if not matches:
            raise ProviderError(f"No JIRA user matches '{assignee}'.")
        if len(matches) > 1:
            names = ", ".join(m.get("displayName", "?") for m in matches[:5])
            raise ProviderError(
                f"'{assignee}' matches several JIRA users ({names}). Be more specific."
            )
        return {"accountId": matches[0]["accountId"]}

    def create_ticket(self, draft: TicketDraft) -> Ticket:
        project = draft.container or self.config.get("project")
        if not project:
            raise ProviderError(
                f"Which project? Pass --in PROJECT, or set 'project' on "
                f"source '{self.source}'."
            )
        fields: dict = {
            "project": {"key": str(project)},
            "summary": draft.title,
            "issuetype": {
                "name": draft.type or self.config.get("default-type", "Task")
            },
        }
        if draft.body:
            fields["description"] = self._body(draft.body)
        if draft.labels:
            fields["labels"] = list(draft.labels)
        if draft.assignee:
            fields["assignee"] = self._user_ref(draft.assignee)
        created = self.request(
            "POST", f"{self.api}/issue", json={"fields": fields}
        ).json()
        return self.get_ticket(created["key"])

    def update_ticket(self, key: str, changes: TicketChanges) -> Ticket:
        payload: dict = {}
        fields: dict = {}
        if changes.title is not None:
            fields["summary"] = changes.title
        if changes.body is not None:
            fields["description"] = self._body(changes.body)
        if fields:
            payload["fields"] = fields
        operations = [{"add": name} for name in changes.add_labels]
        operations += [{"remove": name} for name in changes.remove_labels]
        if operations:
            payload["update"] = {"labels": operations}
        self.request("PUT", f"{self.api}/issue/{key}", json=payload)
        return self.get_ticket(key)

    def add_comment(self, key: str, body: str) -> Comment:
        created = self.request(
            "POST", f"{self.api}/issue/{key}/comment", json={"body": self._body(body)}
        ).json()
        return self._comment(created)

    def assign(self, key: str, assignee: str | None) -> Ticket:
        if assignee:
            payload = self._user_ref(assignee)
        else:
            payload = {"accountId": None} if self.cloud else {"name": None}
        self.request("PUT", f"{self.api}/issue/{key}/assignee", json=payload)
        return self.get_ticket(key)

    def transition(self, key: str, status: str) -> Ticket:
        path = f"{self.api}/issue/{key}/transitions"
        available = self.request("GET", path).json().get("transitions", [])
        wanted = status.strip().lower()
        for candidate in available:
            names = {
                candidate.get("name", "").lower(),
                (candidate.get("to") or {}).get("name", "").lower(),
            }
            if wanted in names:
                self.request("POST", path, json={"transition": {"id": candidate["id"]}})
                return self.get_ticket(key)
        options = ", ".join(
            (t.get("to") or {}).get("name") or t.get("name", "?") for t in available
        )
        raise ProviderError(
            f"{key} cannot move to '{status}' from here. "
            f"Available: {options or 'nothing — the workflow offers no transitions'}."
        )
