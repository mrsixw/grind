# Usage Guide

## Basic usage

```bash
grind                       # same as: grind greet
grind greet --name Alice
grind --theme rainbow
grind --no-colour
```

Global options (`--theme`, `--no-colour`, `--config`, …) go before the
subcommand; they are resolved once and shared with every command.

## Themes

```bash
grind --theme default
grind --theme dark
grind --theme light
grind --theme mono       # no colour
grind --theme rainbow    # cycling ROYGBIV
```

## Seasonal colours

Seasonal colours are on by default. They change automatically around holidays:

```bash
grind                                  # western calendar (default)
grind --seasonal-calendar jewish       # Hanukkah, Passover, etc.
grind --no-seasonal-colours            # disable entirely
```

## Config file

```bash
grind config init               # write ~/.config/grind/config.toml
grind config show               # print resolved config
grind --config my.toml greet    # use a custom config file
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
