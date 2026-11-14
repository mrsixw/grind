# Getting Started with grind

From nothing to your first cup: install, point grind at your ticket systems,
and list what is on your plate.

## 1. Install

```bash
curl -sSL https://raw.githubusercontent.com/mrsixw/grind/main/install.sh | bash
```

This installs the `grind` executable, its man page, and shell completions.
Python 3.11 or newer must be on your `PATH`.

## 2. Create a config file

```bash
grind config init
```

This writes `~/.config/grind/config.toml` with every option commented out.

## 3. Add your sources

A **source** is one place tickets come from. Add a table for each at the
bottom of the config file. The table's name is yours to choose; it becomes the
prefix of every ticket reference from that source.

### GitHub Issues

```toml
[sources.oss]
provider = "github"
repo = "acme/beans"      # optional: the default repository
```

Create a token at **GitHub → Settings → Developer settings → Personal access
tokens** with read and write access to issues, then export it:

```bash
export GITHUB_TOKEN=github_pat_...
```

`GH_TOKEN` is tried first, then `GITHUB_TOKEN`. For GitHub Enterprise, add
`url = "https://ghe.example.com/api/v3"`.

### JIRA Cloud

```toml
[sources.work]
provider = "jira"
url = "https://acme.atlassian.net"
user = "you@acme.example"
project = "PROJ"         # optional: the default project
```

Create an API token at **Atlassian account → Security → API tokens**, then:

```bash
export JIRA_TOKEN=...
```

### JIRA Server or Data Center

```toml
[sources.dc]
provider = "jira"
url = "https://jira.acme.example"
api-version = 2
```

Leave `user` out and export a personal access token as `JIRA_TOKEN`.

### Several sources of the same kind

Give each its own token variable with `token-env`:

```toml
[sources.client]
provider = "jira"
url = "https://client.atlassian.net"
user = "you@acme.example"
token-env = "CLIENT_JIRA_TOKEN"
```

Tokens are only ever read from the environment. Nothing secret goes in the
config file.

## 4. Check it works

```bash
grind sources --check
```

Each source reports the account its token belongs to, or the reason it was
turned away.

## 5. Grind

```bash
grind                       # your open tickets, everywhere
grind show work:PROJ-123
grind move work:PROJ-123 "In Progress"
```

The [Usage guide](usage.md) covers every command, and the
[Options reference](options.md) every flag and config key.

## 6. Something other than JIRA or GitHub?

Any system with an HTTP API can be added as a provider plugin — see
[Writing a provider](plugins.md).
