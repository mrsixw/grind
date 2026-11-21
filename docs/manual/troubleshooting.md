# Troubleshooting

## "No sources configured"

grind has nowhere to fetch tickets from. Run `grind config init`, then add a
`[sources.<name>]` table — see [Getting started](getting-started.md).

## "No token for source ..."

The environment variable holding that source's token is unset. The message
names the variables it tried. Set one, or point the source at a different
variable with `token-env`.

## A source answers 401, 403 or 404

- **401** — the token is wrong or expired. For JIRA Cloud, check `user` is
  the email address the API token belongs to.
- **403** — the token is valid but lacks permission for that action, such as
  a read-only token used with `create`.
- **404** — the ticket does not exist, or the token cannot see it. Both look
  the same from outside.

`grind sources --check` tests every source at once.

## "Which source is ... from?"

With more than one source configured, references need their prefix:
`work:PROJ-123`, not `PROJ-123`.

## JIRA will not `move` a ticket

JIRA workflows only allow certain transitions from each status. The error
lists the ones available from where the ticket is now.

## A provider plugin does not show up in `grind sources`

- It must be installed where grind can import it:
  `pip install --target "$(grind sources --plugin-dir)" <package>`.
- Its `pyproject.toml` must register an entry point in the `grind.providers`
  group. See [Writing a provider](plugins.md).

## No colour output

If you see no colours, check:

- Are you using `--no-colour` or `GRIND_NO_COLOUR=1`?
- Does your terminal support ANSI colours?
- Try `--theme default` explicitly.

## Seasonal colours not showing

- Seasonal colours only appear on themed dates. Check today's date and the calendar you're using.
- Try `--seasonal-calendar western` to use the default calendar.
- Pass `--no-seasonal-colours` to disable entirely.

## Config file not found

Run `grind config init` to create a default config at `~/.config/grind/config.toml`.

Use `grind config show` to see which config file is being used and what keys are set.

## Update check fails silently

The update check is non-fatal. If it fails (no network, GitHub rate limit),
grind continues normally. Pass `--no-update-check` to skip it entirely.

## Command not found after install

Add `~/.local/bin` to your PATH:

```bash
export PATH="${HOME}/.local/bin:${PATH}"
```

## `Another grind shadows this install`

The installer put the binary in `~/.local/bin`, but a different copy sits earlier in your `PATH` and wins every invocation. The installer names both paths and exits non-zero rather than reporting a success you cannot use.

This is the usual cause of two otherwise baffling symptoms:

- `grind completions bash` fails with `No such command 'completions'` — the shadowing copy predates the subcommand.
- `grind update` appears to do nothing, because it updates a copy you never actually run.

Confirm which binary you are running, then remove the rogue copy:

```bash
command -v grind        # the one that actually runs
rm "$(command -v grind)"
```

Re-run `install.sh` afterwards to confirm the warning is gone. If you would rather keep the other copy, reorder `PATH` so `~/.local/bin` comes first instead.
