# Writing a provider

A **provider** teaches grind to talk to one kind of ticket system. JIRA and
GitHub are built in; anything else with an HTTP API is a small Python class.

## The smallest plugin

```python
# grind_kettle.py
from grind.providers import HttpProvider
from grind.tickets import ListQuery, Ticket


class KettleProvider(HttpProvider):
    name = "kettle"                        # provider = "kettle" in the config
    default_token_env = ("KETTLE_TOKEN",)  # where the token is read from

    def _ticket(self, raw: dict) -> Ticket:
        return Ticket(
            source=self.source,
            key=str(raw["id"]),
            title=raw["subject"],
            status=raw["state"],
            is_open=raw["state"] != "resolved",
            assignee=raw.get("owner", ""),
            url=f"{self.base_url}/tickets/{raw['id']}",
            updated=raw.get("updated_at", ""),
        )

    def list_tickets(self, query: ListQuery) -> list[Ticket]:
        params = {"limit": query.limit, "q": query.text}
        if query.mine:
            params["owner"] = "me"
        if query.state != "all":
            params["state"] = query.state
        rows = self.request("GET", "/api/tickets", params=params).json()
        return [self._ticket(row) for row in rows]

    def get_ticket(self, key: str, *, comments: bool = False) -> Ticket:
        return self._ticket(self.request("GET", f"/api/tickets/{key}").json())
```

That is a complete, read-only provider. `list` and `show` work; the write
commands answer "the 'kettle' provider does not support …" until you
implement them.

## Registering it

Declare the class under the `grind.providers` entry-point group:

```toml
# pyproject.toml of your plugin package
[project]
name = "grind-kettle"
version = "0.1.0"
dependencies = []

[project.entry-points."grind.providers"]
kettle = "grind_kettle:KettleProvider"
```

## Installing it

grind ships as a self-contained executable, so plugins go in its plugin
directory rather than a virtualenv:

```bash
pip install --target "$(grind sources --plugin-dir)" ./grind-kettle
grind sources          # kettle now appears under PROVIDER
```

If you run grind from a virtualenv instead (`uv run grind`), installing the
plugin into the same environment works too.

Then use it like any other provider:

```toml
[sources.office]
provider = "kettle"
url = "https://kettle.acme.example"
```

## What `HttpProvider` gives you

| | |
| --- | --- |
| `self.request(method, path, **kwargs)` | One authenticated call. `path` is joined onto the source's `url`; an absolute URL is used as-is, for following pagination links. Returns the `requests.Response`, or raises `ProviderError` with a readable message on connection failures and on any 4xx/5xx |
| `self.token()` | The token, from `token-env` in the source config, else `default_token_env` |
| `self.auth()` | Override when a bearer token is not what the API wants. Return anything `requests` accepts as `auth=` — a `(user, password)` tuple, or a callable |
| `self.error_detail(response)` | Override to pull the API's own error message out of an error body |
| `self.config` | The source's `[sources.<name>]` table, for your own keys |
| `self.require("key")` | A config value, or a `ProviderError` naming the missing key |
| `self.session` | The `requests.Session`, for default headers |
| `default_url` | Class attribute: the URL used when the source sets none |

For something that is not HTTP at all, subclass `grind.providers.Provider`
directly.

## The operations

Only the first two are required.

| Method | Command |
| ------ | ------- |
| `list_tickets(query: ListQuery) -> list[Ticket]` | `list` |
| `get_ticket(key, *, comments=False) -> Ticket` | `show` |
| `whoami() -> str` | `sources --check` |
| `create_ticket(draft: TicketDraft) -> Ticket` | `create` |
| `update_ticket(key, changes: TicketChanges) -> Ticket` | `edit` |
| `add_comment(key, body) -> Comment` | `comment` |
| `assign(key, assignee) -> Ticket` | `assign` — `assignee` is a name, `tickets.ME`, or `None` to unassign |
| `transition(key, status) -> Ticket` | `move` |

The dataclasses live in `grind.tickets`. In a `ListQuery`, `container` is
whatever your system files tickets under — a project, a board, a queue.

## Rules of the road

- **Raise `ProviderError`** for anything the user can act on. Its message is
  printed as-is; any other exception is a bug and shows a traceback.
- **Never print.** Return data; the CLI decides what goes to stdout.
- **Never log or echo the token.**
- **Keys must not need a colon-prefixed source name** — grind strips
  `<source>:` before your provider sees the key.
- A plugin cannot replace a built-in: `provider = "github"` always means the
  one that ships with grind.
