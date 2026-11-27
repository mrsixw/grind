# Usage Guide

## Basic usage

```bash
grind                       # same as: grind list
grind list --state all      # open and closed
grind --theme rainbow list
grind --no-colour list
```

Global options (`--theme`, `--no-colour`, `--config`, …) go before the
subcommand; they are resolved once and shared with every command.

## Sources and ticket references

A **source** is one place tickets come from: a `[sources.<name>]` table in the
config file. The name is yours to choose, and it prefixes every ticket
reference:

| Reference | Meaning |
| --------- | ------- |
| `work:PROJ-123` | JIRA issue `PROJ-123` on the source named `work` |
| `oss:acme/beans#7` | GitHub issue 7 in `acme/beans` on the source named `oss` |
| `oss:#7` | The same, when the source sets `repo = "acme/beans"` |
| `PROJ-123` | Allowed without a prefix when only one source is configured |

```bash
grind sources               # what is configured, and which providers exist
grind sources --check       # test each source's credentials
```

## Listing tickets

```bash
grind list                          # mine, open, every source
grind list -s work                  # one source (repeat -s for several)
grind list --everyone --in PROJ     # everyone's, in one project or repo
grind list -s oss --in mrsixw       # every repo an org or user owns
grind list -s work --in PROJ --in OPS  # several JIRA projects at once
grind list --state closed -q beans  # free-text search
grind list --limit 10 --format json | jq '.[].ref'
```

A line on stderr says what is being listed, for example `Grinding through open
tickets assigned to you in oss; for everyone in work...`, so a filtered list
never passes for the whole queue. Set `mine = false` on a source to make
everyone's tickets its default.

Tickets are merged across sources and sorted by last update. If one source
fails, the others are still printed, a warning goes to stderr, and the exit
code is 1.

## Reading a ticket

```bash
grind show work:PROJ-123
grind show work:PROJ-123 --comments --format json
```

## Creating and changing tickets

```bash
grind create -s work -t "Order more beans" -b "We are nearly out." --type Task
grind create -s oss -t "Descale the machine" -l chore -a @me --in acme/beans
git log -5 | grind create -s work -t "Release notes" --body-file -

grind edit work:PROJ-123 -t "Order more beans (dark roast)"
grind edit oss:#7 --add-label urgent --remove-label stale

grind comment work:PROJ-123 "Ordered. Arrives Tuesday."

grind assign oss:#7                 # to yourself
grind assign work:PROJ-123 grace    # to someone else
grind assign oss:#7 --nobody        # unassign

grind move work:PROJ-123 "In Progress"
grind move oss:#7 done              # GitHub: open, closed/done, not-planned
```

Every write command prints the ticket's reference on stdout and its
confirmation on stderr, so they compose:

```bash
grind show "$(grind create -s work -t 'Order more beans')"
```

`move` speaks each system's own vocabulary. For JIRA it accepts either the
target status or the transition's name, and lists what the workflow allows
when the move is not possible.

## Themes

```bash
grind --theme default    # coffee: mocha, caramel and latte (the default)
grind --theme dark
grind --theme light
grind --theme mono       # no colour
grind --theme rainbow    # cycling ROYGBIV
```

## Seasonal colours

Seasonal colours are on by default. Around holidays they take over from the
theme; the rest of the year you see the theme:

```bash
grind                                  # western calendar (default)
grind --seasonal-calendar jewish       # Hanukkah, Passover, etc.
grind --no-seasonal-colours            # disable entirely
```

## Config file

```bash
grind config init               # write ~/.config/grind/config.toml
grind config show               # print resolved config
grind --config my.toml list     # use a custom config file
```

## Shell completions

```bash
eval "$(grind completions bash)"   # bash
eval "$(grind completions zsh)"    # zsh
grind completions fish | source    # fish
```

`install.sh` installs these permanently and prints the one line your shell
needs to load them. Dropping the files into place is not enough on its own:
zsh wants the directory on `fpath` above `compinit`, and bash wants either the
`bash-completion` package or an explicit `source`. Only fish needs nothing.

## Updating

```bash
grind update                       # fetch and install the latest release
```

Replaces the running executable in place, atomically — an interrupted download
leaves the working binary untouched. Re-run `install.sh` if you also want a
refreshed man page.

## Caching

```bash
grind --cache                      # enable caching
grind --cache --cache-ttl 10m      # cache for 10 minutes
grind --no-cache                   # disable caching
```

Only `list` results are cached, per source and per query. Changing a source's
config changes its cache key, so an edited source never serves stale tickets.
Write commands and `show` always go to the source.
