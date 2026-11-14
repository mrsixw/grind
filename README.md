# ☕ grind

[![CI](https://github.com/mrsixw/grind/actions/workflows/ci.yml/badge.svg)](https://github.com/mrsixw/grind/actions/workflows/ci.yml)

**Your tickets, freshly ground from every source.** One terminal queue for
JIRA, GitHub Issues, and anything else with an HTTP API.

The daily grind is the tickets. `grind` pours them all into one cup: list what
is on your plate across every system you work in, then create, edit, comment
on, assign and move tickets without leaving the terminal.

> **Status:** the commands, the provider interface and plugin loading are in
> place, but the built-in GitHub and JIRA providers are stubs that say so when
> used. Their API calls follow in the next change.

```text
$ grind
TICKET            STATUS       ASSIGNEE      UPDATED     TITLE
work:PROJ-123     In Progress  Ada Lovelace  2026-11-05  Order more beans
oss:acme/beans#7  open         ada           2026-11-01  Descale the espresso machine
```

## What it does

| | |
| --- | --- |
| **One queue** | `grind` lists your open tickets from every configured source, newest first |
| **Full CRUD** | `create`, `show`, `edit`, `comment`, `assign` and `move`, with the same verbs for every system |
| **JIRA** | Cloud (REST v3), Server and Data Center (REST v2) |
| **GitHub Issues** | github.com and GitHub Enterprise |
| **Pluggable** | Any other system is a small Python class registered through an entry point — see [Writing a provider](docs/manual/plugins.md) |
| **Scriptable** | Data on stdout, chatter on stderr, `--format json`, and write commands print the ticket reference |
| **Safe by default** | Tokens are read from the environment, never from the config file |

## Installation

```bash
curl -sSL https://raw.githubusercontent.com/mrsixw/grind/main/install.sh | bash
```

Or build and install from source:

```bash
git clone https://github.com/mrsixw/grind.git
cd grind
make build
sudo make install
```

*(Note: This compiles and installs the CLI locally from your source checkout. If you want to download and install a pre-compiled binary instantly instead, use the `install.sh` script above).*

By default, this installs the executable to `/usr/local/bin`. You can customize the installation prefix using the `PREFIX` variable:

```bash
make install PREFIX=$HOME/.local
```

To uninstall:

```bash
sudo make uninstall
```

If installed with a custom `PREFIX`:

```bash
make uninstall PREFIX=$HOME/.local
```

## Quick start

```bash
grind config init                    # write ~/.config/grind/config.toml
$EDITOR ~/.config/grind/config.toml  # add a [sources.<name>] table or two
export GITHUB_TOKEN=... JIRA_TOKEN=...
grind sources --check                # are the credentials good?

grind                                # my open tickets, everywhere
grind list --all --in PROJ -q beans  # search a project
grind show work:PROJ-123 --comments
grind create -s work -t "Order more beans" --type Task
grind comment work:PROJ-123 "Ordered. Arrives Tuesday."
grind assign oss:#7                  # to me
grind move work:PROJ-123 "In Progress"
grind move oss:#7 done
```

A minimal config:

```toml
[sources.oss]
provider = "github"
repo = "acme/beans"

[sources.work]
provider = "jira"
url = "https://acme.atlassian.net"
user = "you@acme.example"
project = "PROJ"
```

See the **[Getting Started guide](docs/manual/getting-started.md)** for the full
walkthrough.

## Development

```bash
uv sync --extra dev
make format && make lint && make test
```

## Documentation

- [Getting started](docs/manual/getting-started.md)
- [Options reference](docs/manual/options.md)
- [Usage guide](docs/manual/usage.md)
- [Writing a provider](docs/manual/plugins.md)
- [Troubleshooting](docs/manual/troubleshooting.md)
- [Contributing](CONTRIBUTING.md)
