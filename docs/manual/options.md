# Options Reference

`grind` is a command group. The options below are **global**: they go
before the subcommand (`grind --theme rainbow list`), are resolved once
against the config file, and are shared with every subcommand through a single
settings object — so new commands never need their own copies of these flags.

## Commands

### `list`

List tickets across your sources. The default when no subcommand is given.

| Option | Meaning |
| ------ | ------- |
| `-s`, `--source NAME` | Only this source. Repeatable. Default: every source |
| `--mine` / `--all` | Tickets assigned to you (default), or to anyone |
| `--state open\|closed\|all` | Which tickets to include. Default: `open` |
| `-q`, `--query TEXT` | Free-text search |
| `--in PROJECT` | Project or repository, overriding the source's default |
| `--limit N` | Most tickets to fetch per source. Config key: `limit = 50` |
| `--format table\|json` | Output format. Config key: `format = "table"` |

Exits 1 if any source failed, after printing what the others returned.

### `show REF [--comments] [--format table|json]`

Show one ticket, optionally with its comments. Field names are bold, in the
theme's label colour, and their values are in its value colour: a pair that
contrasts a little, so the eye can find a field fast. On a holiday the
seasonal colour takes over. Where it cycles (December, Pride, Holi), labels and
values get neighbouring colours; otherwise the bold keeps them apart.

Each field has an emoji in front of it:

```text
oss:acme/beans#7  Descale the espresso machine
  🚦 Status:   open
  🧩 Type:     issue
  👤 Assignee: ada
  📣 Reporter: grace
  🔖 Labels:   chore
  📅 Created:  2026-10-01
  🔄 Updated:  2026-11-01
  🔗 URL:      https://github.com/acme/beans/issues/7
```

[`--no-emoji`](#--emoji----no-emoji) leaves them out. The labels and values
keep their colours.

### `create`

Create a ticket. Prints the new reference on stdout.

| Option | Meaning |
| ------ | ------- |
| `-s`, `--source NAME` | Where to create it. Optional with a single source |
| `-t`, `--title TEXT` | Title. Required |
| `-b`, `--body TEXT` | Description |
| `--body-file PATH` | Read the description from a file, `-` for stdin |
| `--type NAME` | Ticket type, e.g. `Bug`. JIRA only; default `default-type` or `Task` |
| `-l`, `--label NAME` | Label. Repeatable |
| `-a`, `--assignee USER` | Assignee. `@me` for yourself |
| `--in PROJECT` | Project or repository, overriding the source's default |

### `edit REF`

Change a ticket's title (`-t`), description (`-b` or `--body-file`), or labels
(`--add-label`, `--remove-label`, both repeatable). At least one is required.

### `comment REF [BODY] [--body-file PATH]`

Add a comment.

### `assign REF [USER] [--nobody]`

Assign a ticket. With no `USER` it is assigned to you; `--nobody` unassigns.

### `move REF STATUS`

Move a ticket to another status. JIRA accepts a target status or a transition
name; GitHub accepts `open`, `reopen`, `closed`, `done` and `not-planned`.

### `sources [--check] [--plugin-dir]`

List the configured sources and every available provider. `--check` calls
each source to confirm its credentials work, and exits 1 if any do not.
`--plugin-dir` prints where provider plugins are installed.

### `config show`

Print the resolved configuration.

### `config init`

Write a default config file to `~/.config/grind/config.toml`.

### `config update`

Merge any options missing from your existing config file in from the
template, writing a timestamped backup first. Useful after upgrading to a
release that introduces new config keys.

### `completions [bash|zsh|fish]`

Print the shell completion script. Eval in your shell config:

```bash
eval "$(grind completions bash)"
```

### `update`

Download the latest release and replace the running executable with it.

```bash
grind update
```

The replacement is atomic, so an interrupted download leaves the working
binary in place. Nothing is written unless a newer release actually exists.

The man page is not refreshed — re-run `install.sh` for that. Completion
scripts need no refresh: they call back into the binary, so they follow it
automatically.

Not to be confused with `config update`, which merges new keys into your
config file, or `--no-update-check`, which silences the passive notice.

## Source configuration

Sources live in the config file only; there are no flags for them.

```toml
[sources.oss]
provider = "github"
repo = "owner/repo"              # optional default repository
token-env = "GITHUB_TOKEN"       # default: GH_TOKEN, then GITHUB_TOKEN
url = "https://api.github.com"   # change for GitHub Enterprise

[sources.work]
provider = "jira"
url = "https://example.atlassian.net"
user = "you@example.com"         # omit for a Server/Data Center PAT
token-env = "JIRA_TOKEN"         # default: JIRA_TOKEN, then JIRA_API_TOKEN
project = "PROJ"                 # optional default project
default-type = "Task"            # issue type used by create
jql = "labels = backend"         # optional extra filter for list
api-version = 3                  # 2 for Server / Data Center
```

`token-env` names an environment variable. The token itself never goes in the
config file, so the file is always safe to commit or paste into a bug report.

TOML requires tables to come after every top-level key, so keep the
`[sources.*]` tables at the bottom of the file.

## Display options

### `--theme`

Set the terminal colour theme. Choices: `default`, `dark`, `light`, `mono`, `rainbow`.

| Theme | Look |
| ----- | ---- |
| `default` | Coffee: mocha rows, caramel headers and field names, latte values and progress, matcha for success, honey for warnings, coffee-cherry red for errors |
| `dark` | Bright blue and magenta, with bright white values, for dark terminals |
| `light` | Blue and green, with black values, for light terminals |
| `mono` | No colour at all |
| `rainbow` | The Pride colours, one per row; magenta field names over cyan values |

The coffee browns are 256-colour shades picked to read on dark and light
backgrounds alike. A terminal limited to 16 colours shows its nearest match.

The theme colours every day the seasonal calendar has nothing to mark. On a
holiday the seasonal colours take over, and the theme returns the day after.

```bash
grind --theme rainbow
grind --theme mono      # no colour
```

Config key: `theme = "default"`

### `--table-style`

Choose how `list` and `sources` draw their tables. Choices: `outline`,
`rounded_outline`, `grid`, `simple`, `github`, `plain`. Default: `outline`,
the same bordered style breakfast uses.

Every app built from the five-clis template offers the same key and the same
choices, so one style can be set everywhere. Each is a
[tabulate](https://github.com/astanin/python-tabulate#table-format) format.

```bash
grind --table-style rounded_outline
grind --table-style plain    # no borders, closest to a bare column layout
```

Titles are clipped with `…` so the table fits the terminal width, measured in
terminal cells, so emoji and other wide characters count double.

Config key: `table-style = "outline"`

### `--emoji` / `--no-emoji`

Put an emoji in front of each field in `show` (enabled by default). `--no-emoji` leaves them out, and nothing else changes:
the labels and values keep their colours, and the values stay lined up.

```text
oss:acme/beans#7  Descale the espresso machine
  Status:   open
  Type:     issue
```

Config key: `emoji = true`

### `--seasonal-colours` / `--no-seasonal-colours`

Apply seasonal ANSI colours based on the current date (enabled by default).
On the holidays and cultural events of the chosen calendar they replace the
theme's colours; on every other day the theme applies as usual. The supported
calendars, and the days each one marks, are listed under
[`--seasonal-calendar`](#--seasonal-calendar).

Config key: `seasonal-colours = true`

### `--seasonal-calendar`

Choose which cultural calendar drives seasonal colours.

| Value | Calendar |
| ----- | -------- |
| `western` | Gregorian holidays (Christmas, Easter, Pride Month, Halloween) |
| `jewish` | Hanukkah, Passover, Rosh Hashanah, Sukkot |
| `islamic` | Eid al-Fitr, Eid al-Adha |
| `hindu` | Diwali, Holi |
| `sikh` | Vaisakhi, Bandi Chhor Divas |
| `east-asian` | Lunar New Year, Mid-Autumn, Songkran, Hanami |
| `rainbow` | The Pride cycle every day of the year, not just in June |
| `off` | No seasonal colours; the `--theme` colours apply instead |

`rainbow` and `off` are the two values that ignore the date. `off` is
equivalent to `--no-seasonal-colours`.

```bash
grind --seasonal-calendar rainbow
grind --seasonal-calendar off
```

Config key: `seasonal-calendar = "western"`

### `--no-colour`

Disable all ANSI colour output. Also honoured via the `GRIND_NO_COLOUR`
environment variable, set to any non-empty value.

Config key: `no-colour = false`

Any one of the flag, the environment variable, or the config key switching
colour off is enough; none of them can switch it back on.

## Config options

### `--config PATH`

Path to a TOML config file. Overrides the XDG default search paths.
It is an error if the file does not exist.

## Caching

### `--cache` / `--no-cache`

Enable disk caching of results (off by default).

Config key: `cache = false`

### `--cache-ttl`

How long to cache results. Accepts seconds (`300`), or suffixed strings (`5m`, `2h`). Default: 300s.

Config key: `cache-ttl = "300"`

### `--no-update-check`

Disable the automatic update check. Also honoured via the
`GRIND_NO_UPDATE_CHECK` environment variable, set to any non-empty value.

Config key: `no-update-check = false`

Any one of the flag, the environment variable, or the config key switching the
check off is enough; none of them can switch it back on.

### Environment variable semantics

Both `GRIND_NO_COLOUR` and `GRIND_NO_UPDATE_CHECK` are resolved by
**presence**, following the [no-color.org](https://no-color.org) convention:
any non-empty value switches the behaviour off, and only unset or empty leaves
it on. The value is never parsed, so `=0` and `=false` still disable — and a
stray `GRIND_NO_COLOUR=maybe` in a shell profile is harmless rather than
fatal.

### `--update-summary` / `--no-update-summary`

Append a short summary of the release highlights to the update notice — the
first few bullet points of the GitHub release body, with headers and bare
URLs stripped, truncated to 200 characters:

```text
🍟 A fresh order is ready! v1.0.2 → v1.0.3 — update at https://github.com/…
  📋 - Added the doctor command - Fixed cache expiry on 32-bit systems
```

Off by default, and has no effect alongside `--no-update-check`. The body is
read from the same 24-hour cache as the version check, so turning this on
costs no extra network round trip.

Config key: `update-summary = false`

## Diagnostics

### `--debug-summary` / `--no-debug-summary`

Print a run summary to stderr once the command finishes — elapsed time, how
much work was done, cache state, and whatever rows the command itself adds:

```text
🐛 Debug summary
  Total elapsed:   0.04s
  Items processed: 12
  Cache:           enabled, ttl 7200s
  Requests to oss: 1
  Requests to work: 2
```

The `Requests to` rows count the upstream API calls each source made, which is
the number to watch when a source is rate-limiting you.

Config key: `debug-summary = false`

## Other

### `--version`

Show the installed version and exit.
