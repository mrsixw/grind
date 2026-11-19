# Providers and sources

How grind talks to several ticket systems through one set of commands.

## The shape

```text
cli.py ──► providers/ ──► github.py   (built-in)
   │           │      ──► jira.py     (built-in)
   │           │      ──► entry points in group "grind.providers" (plugins)
   └──► tickets.py  ◄── every provider translates to and from this model
```

- **`tickets.py`** is the vocabulary: `Ticket`, `Comment`, `ListQuery`,
  `TicketDraft`, `TicketChanges`. It imports nothing from the package.
- **`providers/`** is the plugin API, all importable from `grind.providers`.
  One module per job: `base.py` (the `Provider` interface and
  `ProviderError`), `http.py` (the `HttpProvider` base class), `registry.py`
  (built-ins, entry-point plugins, building sources) and `refs.py` (reference
  parsing).
- **`cli.py`** never names JIRA or GitHub. It resolves a source to a provider
  and speaks only the model. Adding a system never touches it.

## Decisions

### A source is an instance; a provider is a kind

`[sources.work]` with `provider = "jira"` is one JIRA. Two JIRAs are two
sources of the same provider. References are `<source>:<key>` because the
source name is the only thing guaranteed unique, and the key stays in the
system's own spelling so it can be pasted from a browser.

### Only reading is mandatory

`list_tickets` and `get_ticket` are abstract. Every write operation defaults
to raising a `ProviderError` that names the provider and the operation, so a
read-only plugin is complete and its limits are explained rather than crashing.

### Plugins are Python entry points, plus a plugin directory

Third-party providers register under the `grind.providers` entry-point group.
grind is distributed as a shiv zipapp, whose bundled environment cannot see
packages installed elsewhere, so `<XDG_DATA_HOME>/grind/plugins` is appended
to `sys.path` before discovery. `pip install --target` into that directory is
the whole install story.

Built-ins are registered with a decorator rather than through entry points,
so they work even from a source checkout with no installed metadata, and a
plugin cannot shadow them: a config that says `github` means the same thing
on every machine.

### Tokens come from the environment only

A source names an environment variable with `token-env`; it never holds the
token. The config file is therefore always safe to commit, and `config show`
has nothing to redact.

### One failing source does not sink the list

`list` collects from each source in turn. A `ProviderError` from one is
printed as a warning on stderr, the rest are still rendered, and the exit code
is 1 so a script can tell the list is incomplete.

### Writes print the reference

`create`, `edit`, `assign` and `move` print only `<source>:<key>` on stdout,
with the human confirmation on stderr, so commands compose in a pipeline.

### The cache covers `list` only

Reads of a single ticket and all writes go straight to the source. The cache
key hashes the source's config together with the query, so editing a source
invalidates its entries.

## Provider notes

### GitHub

- Listing uses the search API (`/search/issues`), the one endpoint that
  expresses "assigned to me", a repository, a state and free text together.
- Pull requests are issues to the REST API; `is:issue` excludes them from
  lists and `show` refuses one explicitly.
- The label API replaces the whole set, so `edit --add-label` reads the
  current labels first.
- Issue types are not supported; `create --type` is refused with a pointer to
  `--label`.

### JIRA

- Cloud is REST v3: Atlassian Document Format for bodies, account ids for
  users, and the token-paginated `/search/jql`. Server and Data Center are
  REST v2: plain strings, usernames, and `startAt` paging on `/search`.
- ADF to text is deliberately lossy; text to ADF produces paragraphs and hard
  breaks only.
- Open versus closed is the status *category* (`statusCategory != Done`), so
  custom workflows need no configuration.
- `move` fetches the transitions the workflow allows from the ticket's current
  status and matches the request against both the transition name and its
  target status.
- An unbounded search is refused client-side with advice, before Cloud
  refuses it with less.

## Not done yet

- Deleting tickets. GitHub's REST API cannot, and it is rarely what anyone
  means; `move` to a closed status is the supported way to retire a ticket.
- Editing or deleting comments.
- JIRA custom fields on `create`.
- Concurrent fetching across sources.
- OAuth. Tokens only.
