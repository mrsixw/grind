"""grind — your tickets, freshly ground from every source.

Structure: ``main`` is a Click group. Its callback resolves global flags
against the config file once, into a single :class:`Settings` object stored
on ``ctx.obj``. Subcommands declare ``@click.pass_obj`` and receive that one
object.

The ticket commands never talk to JIRA or GitHub themselves. They resolve a
source to a :class:`~grind.providers.Provider` and speak only the model in
``tickets.py``, which is what lets a plugin add a new system without touching
this file.
"""

import hashlib
import json
import os
import random
import shutil
import sys
import time
from dataclasses import asdict
from enum import StrEnum, auto

import click

# Imported for their side effect: each registers a built-in provider.
from . import github, jira  # noqa: F401
from .cache import parse_ttl, read_cache, write_cache
from .config import load_config, show_config, update_config, write_default_config
from .constants import (
    APP_ITEMS,
    APP_NAME,
    BINARY_NAME,
    DEFAULT_CACHE_TTL,
    DEFAULT_TABLE_STYLE,
    ENVVAR_PREFIX,
    TABLE_STYLES,
)
from .logger import configure as configure_logging
from .providers import (
    Provider,
    ProviderError,
    available_providers,
    build_sources,
    plugin_dir,
    resolve_ref,
)
from .settings import Settings
from .tables import render_table
from .tickets import ME, STATES, ListQuery, Ticket, TicketChanges, TicketDraft
from .ui import (
    CALENDAR_NAMES,
    THEME_NAMES,
    get_random_cake_recipe,
    get_random_coffee_recipe,
    get_random_pastry_recipe,
    get_theme,
    has_shown_holiday_gift,
    is_birthday,
    is_christmas,
    mark_holiday_gift_shown,
    render_cake_recipe,
    render_coffee_recipe,
    render_pastry_recipe,
)
from .updater import UpdateStatus, check_for_update, perform_update

__all__ = [
    "CONFIG_FREE_COMMANDS",
    "env_flag_is_set",
    "finish_run",
    "main",
    "resolve_option",
]

_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

# Subcommands that must run before, and independently of, config resolution.
CONFIG_FREE_COMMANDS = frozenset({"completions", "update"})


def env_flag_is_set(name: str) -> bool:
    """Report whether an environment variable is set to any non-empty value.

    This is the no-color.org convention: presence is the signal and the value
    is deliberately ignored, so ``GRIND_NO_COLOUR=0`` disables colour just
    as ``=1`` does.

    Click's ``envvar=`` on a boolean flag cannot express this. It routes the
    value through the BOOL converter, so ``=false`` reads as "leave it on" —
    the opposite of the spec — and an unrecognised value aborts the run
    outright. A typo in a shell profile should be ignored, not fatal.
    """
    return bool(os.environ.get(name))


def resolve_option(flag_value, cfg: dict, key: str, default):
    """Resolve an option: CLI flag beats config file beats *default*."""
    if flag_value is not None:
        return flag_value
    return cfg.get(key, default)


@click.group(context_settings=_CONTEXT_SETTINGS, invoke_without_command=True)
@click.version_option(package_name=APP_NAME)
# ── Config ─────────────────────────────────────────────────────────────────
@click.option(
    "--config",
    "config_path",
    default=None,
    metavar="PATH",
    help="Path to a TOML config file.",
)
# ── Display ─────────────────────────────────────────────────────────────────
@click.option(
    "--theme",
    type=click.Choice(THEME_NAMES, case_sensitive=False),
    default=None,
    help=f"Colour theme. Choices: {', '.join(THEME_NAMES)}.",
)
@click.option(
    "--seasonal-colours/--no-seasonal-colours",
    default=None,
    help="Apply seasonal ANSI colours based on the current date.",
)
@click.option(
    "--seasonal-calendar",
    type=click.Choice(CALENDAR_NAMES, case_sensitive=False),
    default=None,
    help="Which cultural calendar drives seasonal colours (default: western).",
)
@click.option(
    "--table-style",
    type=click.Choice(TABLE_STYLES),
    default=None,
    help=f"How tables are drawn. Default: {DEFAULT_TABLE_STYLE}.",
)
@click.option(
    "--no-colour",
    "no_colour",
    is_flag=True,
    default=False,
    # No envvar= here: Click would route GRIND_NO_COLOUR through its BOOL
    # converter, so unrecognised values abort the run. Resolved by presence in
    # the callback instead — see env_flag_is_set.
    help=(
        "Disable all ANSI colour output."
        f" Also honoured via {ENVVAR_PREFIX}_NO_COLOUR, set to any"
        " non-empty value."
    ),
)
# ── Caching ─────────────────────────────────────────────────────────────────
@click.option(
    "--cache/--no-cache",
    "cache_enabled",
    default=None,
    help="Enable disk caching of results (off by default).",
)
@click.option(
    "--cache-ttl",
    default=None,
    metavar="TTL",
    help="Cache TTL: seconds (300), or suffixed (5m, 2h). Default: 300.",
)
# ── Updates ─────────────────────────────────────────────────────────────────
@click.option(
    "--no-update-check",
    is_flag=True,
    default=False,
    # No envvar= here — see the note on --no-colour.
    help=(
        "Disable the automatic update check."
        f" Also honoured via {ENVVAR_PREFIX}_NO_UPDATE_CHECK, set to any"
        " non-empty value."
    ),
)
@click.option(
    "--update-summary/--no-update-summary",
    default=None,
    help="Include release highlights in the update notice.",
)
# ── Diagnostics ─────────────────────────────────────────────────────────────
@click.option(
    "--debug-summary/--no-debug-summary",
    default=None,
    help="Print a run summary (timing, work done) to stderr when finished.",
)
# ── Easter eggs ─────────────────────────────────────────────────────────────
@click.option(
    "--brew",
    is_flag=True,
    default=False,
    hidden=True,
    help="Secret coffee recipe easter egg.",
)
@click.option(
    "--cake",
    is_flag=True,
    default=False,
    hidden=True,
    help="Secret cake recipe easter egg.",
)
@click.option(
    "--pastry",
    is_flag=True,
    default=False,
    hidden=True,
    help="Secret croissant and pain au chocolat easter egg.",
)
@click.pass_context
def main(
    ctx,
    config_path,
    theme,
    seasonal_colours,
    seasonal_calendar,
    table_style,
    no_colour,
    cache_enabled,
    cache_ttl,
    no_update_check,
    update_summary,
    debug_summary,
    brew,
    cake,
    pastry,
):
    """☕ grind — your tickets, freshly ground from every source.

    One queue for JIRA, GitHub and anything else with an HTTP API. Configure
    your sources with ``grind config init``, then see what is on your plate.

    Running with no subcommand is equivalent to ``grind list``.
    """
    # Before anything else, so the elapsed row covers config resolution too.
    started_at = time.monotonic()
    configure_logging()

    # Resolved by presence, not parsed: see env_flag_is_set. Composed with
    # the flag, and for the update check with the config key below too, so any
    # one of them switching it off is enough and none can switch it back on.
    no_colour = no_colour or env_flag_is_set(f"{ENVVAR_PREFIX}_NO_COLOUR")
    no_update_check = no_update_check or env_flag_is_set(
        f"{ENVVAR_PREFIX}_NO_UPDATE_CHECK"
    )

    # completions and update must stay usable when the config file is broken.
    # The shell runs the completion script on every tab-press, so a config error
    # would spew into the user's prompt; and if a bad config could block update,
    # there would be no way to install the release that fixes it.
    if ctx.invoked_subcommand in CONFIG_FREE_COMMANDS:
        return

    try:
        cfg = load_config(config_path)
        ttl = parse_ttl(resolve_option(cache_ttl, cfg, "cache-ttl", DEFAULT_CACHE_TTL))
        style = _table_style(
            resolve_option(table_style, cfg, "table-style", DEFAULT_TABLE_STYLE)
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    theme_name = resolve_option(theme, cfg, "theme", "default")
    ctx.obj = Settings(
        cfg=cfg,
        config_path=config_path,
        theme_name=theme_name,
        theme=get_theme(theme_name),
        seasonal_colours=resolve_option(
            seasonal_colours, cfg, "seasonal-colours", True
        ),
        seasonal_calendar=resolve_option(
            seasonal_calendar, cfg, "seasonal-calendar", "western"
        ),
        colour=not (no_colour or cfg.get("no-colour", False)),
        table_style=style,
        cache_enabled=resolve_option(cache_enabled, cfg, "cache", False),
        cache_ttl=ttl,
        update_check=not (no_update_check or cfg.get("no-update-check", False)),
        update_summary=resolve_option(update_summary, cfg, "update-summary", False),
        debug_summary=resolve_option(debug_summary, cfg, "debug-summary", False),
        brew=brew,
        cake=cake,
        pastry=pastry,
        started_at=started_at,
    )

    if ctx.invoked_subcommand is None:
        ctx.invoke(list_tickets)


def _table_style(name: str) -> str:
    """Validate a table style that may have come from the config file.

    The flag is checked by its ``click.Choice``; the config value is not, and
    a typo there must fail with the choices rather than a tabulate traceback.
    """
    if name not in TABLE_STYLES:
        raise ValueError(
            f"Invalid table-style '{name}' in config. "
            f"Choose from: {', '.join(TABLE_STYLES)}."
        )
    return name


def _notify_update(settings: Settings) -> None:
    """Print an update notice to stderr if a newer release is available."""
    if not settings.update_check:
        return
    update_msg = check_for_update(show_summary=settings.update_summary)
    if update_msg:
        click.echo(
            click.style(settings.theme.apply(update_msg), bold=True),
            err=True,
            color=settings.colour,
        )


def _serve_easter_eggs(settings: Settings) -> None:
    """Print the recipe easter eggs, if today or the flags have earned one.

    The once-a-year gifts are gated on colour: they are pure decoration, so a
    user who asked for plain output should not have them appear unbidden.
    The explicit --brew/--cake/--pastry flags are not gated — the user asked.
    All of it goes to stderr, so a piped stdout is never polluted.
    """
    if settings.colour and is_birthday() and not has_shown_holiday_gift("birthday"):
        recipe = get_random_cake_recipe()
        click.echo(
            render_cake_recipe(recipe, occasion="birthday", colour=settings.colour),
            err=True,
            color=settings.colour,
        )
        mark_holiday_gift_shown("birthday")
    elif settings.cake:
        click.echo(
            render_cake_recipe(get_random_cake_recipe(), colour=settings.colour),
            err=True,
            color=settings.colour,
        )

    if settings.colour and is_christmas() and not has_shown_holiday_gift("christmas"):
        recipe = get_random_coffee_recipe()
        click.echo(
            render_coffee_recipe(recipe, occasion="christmas", colour=settings.colour),
            err=True,
            color=settings.colour,
        )
        mark_holiday_gift_shown("christmas")
    elif settings.brew:
        click.echo(
            render_coffee_recipe(get_random_coffee_recipe(), colour=settings.colour),
            err=True,
            color=settings.colour,
        )


def _serve_pastry(settings: Settings) -> None:
    if settings.pastry:
        click.echo(
            render_pastry_recipe(get_random_pastry_recipe(), colour=settings.colour),
            err=True,
            color=settings.colour,
        )


def _print_debug_summary(
    settings: Settings, item_count: int, extra: dict[str, str] | None = None
) -> None:
    """Print a run summary to stderr: timing, work done, and app-specific rows.

    *extra* is where a scaffolded CLI adds its own rows — request counts, rate
    limit headroom, bytes transferred. breakfast's equivalent is spelled
    ``--api-stats`` and fills this slot with REST and GraphQL counters; here
    the flag is named for what it prints, since a template has no API to count.
    """
    elapsed = time.monotonic() - settings.started_at
    rows = {
        "Total elapsed": f"{elapsed:.2f}s",
        "Items processed": str(item_count),
        "Cache": (
            f"enabled, ttl {settings.cache_ttl}s"
            if settings.cache_enabled
            else "disabled"
        ),
        **(extra or {}),
    }
    width = max(len(label) for label in rows)
    title = settings.theme.apply("🐛 Debug summary", role="accent")
    lines = [click.style(title, bold=True)]
    lines += [f"  {label + ':':<{width + 1}} {value}" for label, value in rows.items()]
    click.echo("\n".join(lines), err=True, color=settings.colour)


def finish_run(
    settings: Settings,
    item_count: int = 0,
    extra: dict[str, str] | None = None,
) -> None:
    """Run the end-of-invocation chores every command shares.

    Call this last from any command that produces user-facing output, so the
    notices land after the command's own output rather than interleaved.
    """
    _notify_update(settings)
    _serve_easter_eggs(settings)
    _serve_pastry(settings)
    if settings.debug_summary:
        _print_debug_summary(settings, item_count, extra)


# ── Tickets ─────────────────────────────────────────────────────────────────

_FORMATS = ("table", "json")
_NO_SOURCES = (
    "No sources configured, so there is nothing to grind. Run "
    f"`{BINARY_NAME} config init` and add a [sources.<name>] table."
)


def _fail(exc: ProviderError) -> click.ClickException:
    return click.ClickException(str(exc))


def _load_sources(settings: Settings) -> dict[str, Provider]:
    """Build every configured source, or exit with a pointer to the config."""
    try:
        sources = build_sources(settings.cfg)
    except ProviderError as exc:
        raise _fail(exc) from exc
    if not sources:
        raise click.ClickException(_NO_SOURCES)
    return sources


def _pick_sources(
    sources: dict[str, Provider], names: tuple[str, ...]
) -> dict[str, Provider]:
    unknown = [name for name in names if name not in sources]
    if unknown:
        raise click.ClickException(
            f"Unknown source '{unknown[0]}'. Configured: {', '.join(sources)}."
        )
    return {name: sources[name] for name in names} if names else sources


def _one_source(sources: dict[str, Provider], name: str | None) -> Provider:
    if name:
        return next(iter(_pick_sources(sources, (name,)).values()))
    if len(sources) == 1:
        return next(iter(sources.values()))
    raise click.ClickException(
        f"Which source? Pass --source. Configured: {', '.join(sources)}."
    )


def _resolve(settings: Settings, ref: str) -> tuple[dict, Provider, str]:
    sources = _load_sources(settings)
    try:
        provider, key = resolve_ref(ref, sources)
    except ProviderError as exc:
        raise _fail(exc) from exc
    return sources, provider, key


def _progress(settings: Settings, message: str) -> None:
    click.echo(
        settings.theme.apply(f"{message} {random.choice(APP_ITEMS)}", role="muted"),
        err=True,
        color=settings.colour,
    )


def _request_rows(sources: dict[str, Provider]) -> dict[str, str]:
    return {
        f"Requests to {name}": str(provider.request_count)
        for name, provider in sources.items()
    }


def _format(settings: Settings, output_format: str | None) -> str:
    chosen = resolve_option(output_format, settings.cfg, "format", "table")
    if chosen not in _FORMATS:
        raise click.ClickException(
            f"Invalid format '{chosen}' in config. Choose from: {', '.join(_FORMATS)}."
        )
    return chosen


def _short_date(stamp: str) -> str:
    return stamp[:10]


def _render_tickets(settings: Settings, tickets: list[Ticket]) -> str:
    rows = [
        [t.ref, t.status, t.assignee or "—", _short_date(t.updated), t.title]
        for t in tickets
    ]
    headers = ["TICKET", "STATUS", "ASSIGNEE", "UPDATED", "TITLE"]
    return render_table(settings, headers, rows, shrink=headers.index("TITLE"))


def _render_ticket(settings: Settings, ticket: Ticket) -> str:
    title = f"{ticket.ref}  {ticket.title}"
    painted = settings.paint(title, role="accent")
    lines = [click.style(painted, bold=True) if settings.colour else title]
    facts = {
        "Status": ticket.status,
        "Type": ticket.type,
        "Assignee": ticket.assignee or "—",
        "Reporter": ticket.reporter,
        "Labels": ", ".join(ticket.labels),
        "Created": _short_date(ticket.created),
        "Updated": _short_date(ticket.updated),
        "URL": ticket.url,
    }
    lines += [f"  {label + ':':<10}{value}" for label, value in facts.items() if value]
    if ticket.body:
        lines += ["", ticket.body.rstrip()]
    for comment in ticket.comments:
        heading = f"💬 {comment.author} · {_short_date(comment.created)}"
        lines += ["", settings.paint(heading, role="accent"), comment.body.rstrip()]
    return "\n".join(lines)


def _emit_ticket(settings: Settings, ticket: Ticket, output_format: str) -> None:
    if output_format == "json":
        click.echo(json.dumps(ticket.to_dict(), indent=2))
    else:
        click.echo(_render_ticket(settings, ticket))


def _cached_list(
    settings: Settings, provider: Provider, query: ListQuery
) -> list[Ticket]:
    """List from *provider*, through the disk cache when it is enabled."""
    if not settings.cache_enabled:
        return provider.list_tickets(query)
    # The source's own config is part of the key, so editing a source's url
    # or jql can never serve the old source's tickets.
    material = json.dumps(
        [provider.source, provider.config, asdict(query)], sort_keys=True, default=str
    )
    key = "list-" + hashlib.sha256(material.encode()).hexdigest()[:24]
    cached = read_cache(key, settings.cache_ttl)
    if cached is not None:
        return [
            Ticket(**{**row, "labels": tuple(row["labels"]), "comments": ()})
            for row in cached
        ]
    tickets = provider.list_tickets(query)
    write_cache(key, [{**asdict(t), "labels": list(t.labels)} for t in tickets])
    return tickets


@main.command("list")
@click.option(
    "-s",
    "--source",
    "source_names",
    multiple=True,
    metavar="NAME",
    help="Only this source. Repeatable. Default: every configured source.",
)
@click.option(
    "--mine/--all",
    "mine",
    default=True,
    help="Tickets assigned to you (default), or to anyone.",
)
@click.option(
    "--state",
    type=click.Choice(STATES),
    default="open",
    show_default=True,
    help="Which tickets to include.",
)
@click.option("-q", "--query", "text", default="", help="Free-text search.")
@click.option(
    "--in",
    "container",
    default="",
    metavar="PROJECT",
    help="Project or repository to look in, overriding the source's default.",
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=None,
    help="Most tickets to fetch per source. Default: 50.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(_FORMATS),
    default=None,
    help="Output format. Default: table.",
)
@click.pass_obj
def list_tickets(
    settings: Settings,
    source_names=(),
    mine=True,
    state="open",
    text="",
    container="",
    limit=None,
    output_format=None,
):
    """List tickets across your sources (the default command)."""
    output_format = _format(settings, output_format)
    sources = _pick_sources(_load_sources(settings), tuple(source_names))
    query = ListQuery(
        mine=mine,
        state=state,
        text=text,
        limit=resolve_option(limit, settings.cfg, "limit", 50),
        container=container,
    )
    _progress(settings, "Grinding through your tickets...")

    tickets: list[Ticket] = []
    failed = False
    for provider in sources.values():
        try:
            tickets += _cached_list(settings, provider, query)
        except ProviderError as exc:
            # One source being down must not hide the others' tickets.
            failed = True
            click.echo(
                settings.theme.apply(f"⚠️  {exc}", role="warn"),
                err=True,
                color=settings.colour,
            )
    tickets.sort(key=lambda t: t.updated, reverse=True)

    if output_format == "json":
        click.echo(json.dumps([t.to_dict() for t in tickets], indent=2))
    elif tickets:
        click.echo(_render_tickets(settings, tickets))
    elif not failed:
        click.echo(
            "☕ Nothing to grind. The cup is empty — put the kettle on.", err=True
        )

    finish_run(settings, item_count=len(tickets), extra=_request_rows(sources))
    if failed:
        raise SystemExit(1)


@main.command()
@click.argument("ref")
@click.option("--comments/--no-comments", default=False, help="Include comments.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(_FORMATS),
    default=None,
    help="Output format. Default: table.",
)
@click.pass_obj
def show(settings: Settings, ref: str, comments: bool, output_format: str | None):
    """Show one ticket. REF is <source>:<key>, e.g. work:PROJ-123."""
    output_format = _format(settings, output_format)
    sources, provider, key = _resolve(settings, ref)
    try:
        ticket = provider.get_ticket(key, comments=comments)
    except ProviderError as exc:
        raise _fail(exc) from exc
    _emit_ticket(settings, ticket, output_format)
    finish_run(settings, item_count=1, extra=_request_rows(sources))


def _read_body(body: str | None, body_file) -> str | None:
    if body is not None and body_file is not None:
        raise click.UsageError("Pass --body or --body-file, not both.")
    if body_file is not None:
        return body_file.read()
    return body


def _done(settings: Settings, message: str, sources: dict[str, Provider]) -> None:
    """Report a successful write on stderr; the ticket itself goes to stdout."""
    click.echo(
        settings.theme.apply(message, role="success"), err=True, color=settings.colour
    )
    finish_run(settings, item_count=1, extra=_request_rows(sources))


@main.command()
@click.option("-s", "--source", "source_name", default=None, metavar="NAME")
@click.option("-t", "--title", required=True, help="Ticket title.")
@click.option("-b", "--body", default=None, help="Ticket description.")
@click.option(
    "--body-file",
    type=click.File("r"),
    default=None,
    help="Read the description from a file ('-' for stdin).",
)
@click.option("--type", "ticket_type", default="", help="Ticket type, e.g. Bug.")
@click.option("-l", "--label", "labels", multiple=True, help="Label. Repeatable.")
@click.option(
    "-a", "--assignee", default="", help=f"Who to assign. Use {ME} for yourself."
)
@click.option(
    "--in",
    "container",
    default="",
    metavar="PROJECT",
    help="Project or repository to file it in.",
)
@click.pass_obj
def create(
    settings: Settings,
    source_name,
    title,
    body,
    body_file,
    ticket_type,
    labels,
    assignee,
    container,
):
    """Create a ticket. Prints the new ticket's reference on stdout."""
    sources = _load_sources(settings)
    provider = _one_source(sources, source_name)
    draft = TicketDraft(
        title=title,
        body=_read_body(body, body_file) or "",
        type=ticket_type,
        labels=tuple(labels),
        assignee=assignee,
        container=container,
    )
    try:
        ticket = provider.create_ticket(draft)
    except ProviderError as exc:
        raise _fail(exc) from exc
    # The bare reference, so `grind show "$(grind create ...)"` composes.
    click.echo(ticket.ref)
    _done(settings, f"🫘 Freshly ground: {ticket.title} — {ticket.url}", sources)


@main.command()
@click.argument("ref")
@click.option("-t", "--title", default=None, help="New title.")
@click.option("-b", "--body", default=None, help="New description.")
@click.option(
    "--body-file",
    type=click.File("r"),
    default=None,
    help="Read the new description from a file ('-' for stdin).",
)
@click.option("--add-label", "add_labels", multiple=True, help="Label to add.")
@click.option("--remove-label", "remove_labels", multiple=True, help="Label to remove.")
@click.pass_obj
def edit(settings: Settings, ref, title, body, body_file, add_labels, remove_labels):
    """Edit a ticket's title, description or labels."""
    changes = TicketChanges(
        title=title,
        body=_read_body(body, body_file),
        add_labels=tuple(add_labels),
        remove_labels=tuple(remove_labels),
    )
    if changes.is_empty():
        raise click.UsageError("Nothing to change. Pass at least one option.")
    sources, provider, key = _resolve(settings, ref)
    try:
        ticket = provider.update_ticket(key, changes)
    except ProviderError as exc:
        raise _fail(exc) from exc
    click.echo(ticket.ref)
    _done(settings, f"✏️  Updated {ticket.ref}.", sources)


@main.command()
@click.argument("ref")
@click.argument("body", required=False)
@click.option(
    "--body-file",
    type=click.File("r"),
    default=None,
    help="Read the comment from a file ('-' for stdin).",
)
@click.pass_obj
def comment(settings: Settings, ref, body, body_file):
    """Add a comment to a ticket."""
    text = _read_body(body, body_file)
    if not text or not text.strip():
        raise click.UsageError("A comment needs some words: pass BODY or --body-file.")
    sources, provider, key = _resolve(settings, ref)
    try:
        provider.add_comment(key, text)
    except ProviderError as exc:
        raise _fail(exc) from exc
    _done(settings, f"💬 Comment added to {provider.source}:{key}.", sources)


@main.command()
@click.argument("ref")
@click.argument("user", required=False)
@click.option("--nobody", is_flag=True, help="Unassign the ticket.")
@click.pass_obj
def assign(settings: Settings, ref, user, nobody):
    """Assign a ticket to USER — to yourself when USER is omitted."""
    if nobody and user:
        raise click.UsageError("Pass a USER or --nobody, not both.")
    sources, provider, key = _resolve(settings, ref)
    try:
        ticket = provider.assign(key, None if nobody else (user or ME))
    except ProviderError as exc:
        raise _fail(exc) from exc
    click.echo(ticket.ref)
    who = ticket.assignee or "nobody"
    _done(settings, f"👤 {ticket.ref} is now assigned to {who}.", sources)


@main.command()
@click.argument("ref")
@click.argument("status")
@click.pass_obj
def move(settings: Settings, ref, status):
    """Move a ticket to STATUS, e.g. "In Progress", done, closed."""
    sources, provider, key = _resolve(settings, ref)
    try:
        ticket = provider.transition(key, status)
    except ProviderError as exc:
        raise _fail(exc) from exc
    click.echo(ticket.ref)
    _done(settings, f"➡️  {ticket.ref} is now {ticket.status}.", sources)


@main.command("sources")
@click.option("--check", is_flag=True, help="Test each source's credentials.")
@click.option(
    "--plugin-dir",
    "show_plugin_dir",
    is_flag=True,
    help="Print the directory provider plugins are installed into, and exit.",
)
@click.pass_obj
def list_sources(settings: Settings, check: bool, show_plugin_dir: bool):
    """Show the configured sources and the providers available to them."""
    if show_plugin_dir:
        click.echo(plugin_dir())
        return
    providers = available_providers()
    try:
        sources = build_sources(settings.cfg)
    except ProviderError as exc:
        raise _fail(exc) from exc

    failed = False
    rows = []
    for name, provider in sources.items():
        row = [name, provider.name, getattr(provider, "base_url", "")]
        if check:
            try:
                row.append(f"✅ {provider.whoami()}")
            except ProviderError as exc:
                failed = True
                row.append(f"❌ {exc}")
        rows.append(row)
    if rows:
        headers = ["SOURCE", "PROVIDER", "URL"] + (["CHECK"] if check else [])
        click.echo(render_table(settings, headers, rows))
    else:
        click.echo(_NO_SOURCES, err=True)
    click.echo("")
    click.echo(
        render_table(
            settings, ["PROVIDER", "FROM"], [list(p) for p in providers.items()]
        )
    )
    finish_run(settings, item_count=len(rows), extra=_request_rows(sources))
    if failed:
        raise SystemExit(1)


# ── Config management ───────────────────────────────────────────────────────


@main.group("config")
def config_group():
    """Manage the grind configuration file."""


@config_group.command("show")
@click.pass_obj
def config_show(settings: Settings):
    """Print the resolved configuration."""
    click.echo(show_config(settings.cfg, settings.config_path))


@config_group.command("init")
def config_init():
    """Write a default config file to the XDG config directory."""
    path = write_default_config()
    click.echo(f"✅ Default config written to: {path}")


@config_group.command("update")
@click.pass_obj
def config_update(settings: Settings):
    """Merge missing keys from the template into your config file (with backup)."""
    if not update_config(settings.config_path):
        raise SystemExit(1)


# ── Shell completions ───────────────────────────────────────────────────────


class Shell(StrEnum):
    """A shell that ``completions`` can emit a completion script for.

    ``StrEnum`` + ``auto()`` yields the lowercase member name as the value, so
    members pass straight into Click's completion machinery and into f-strings
    without a trail of ``.value``.
    """

    BASH = auto()
    ZSH = auto()
    FISH = auto()


# Click matches enum choices on member *names*, so click.Choice(Shell) would
# demand "BASH" rather than "bash" — pass the values explicitly instead.
_SHELL_CHOICES = [shell.value for shell in Shell]


@main.command()
@click.argument("shell", type=click.Choice(_SHELL_CHOICES))
def completions(shell: str):
    """Print the shell completion script for SHELL.

    Eval it in your shell config, e.g. ``eval "$(grind completions bash)"``.
    """
    from click.shell_completion import get_completion_class

    comp_cls = get_completion_class(Shell(shell))
    comp = comp_cls(
        cli=main,
        ctx_args={},
        prog_name=BINARY_NAME,
        complete_var=f"_{ENVVAR_PREFIX}_COMPLETE",
    )
    click.echo(comp.source(), nl=False)


# ── Self-update ─────────────────────────────────────────────────────────────


def _current_executable_path() -> str:
    """Resolve the absolute path of the running grind executable.

    ``sys.argv[0]`` is what the user actually invoked, so prefer it whenever it
    names a real file: ``./grind update`` must update *that* copy, not a
    different one that happens to sit earlier on PATH. Fall back to a PATH
    lookup for the usual case, where argv[0] is the bare console-script name.

    ``abspath`` rather than ``resolve`` so a symlinked install has its link
    replaced and not the file it points at, and so a relative argv[0] cannot
    send ``os.replace()`` to the current working directory.
    """
    invoked = sys.argv[0]
    if os.sep in invoked and os.path.isfile(invoked):
        return os.path.abspath(invoked)
    return os.path.abspath(shutil.which(BINARY_NAME) or invoked)


@main.command()
def update():
    """Download and install the latest grind release over this executable."""
    click.echo(
        click.style("🔍 Checking for a newer release...", fg="cyan"),
        err=True,
    )
    status, current, detail = perform_update(_current_executable_path())

    if status is UpdateStatus.UNKNOWN:
        raise click.ClickException("Could not reach GitHub to check for a new release.")
    if status is UpdateStatus.ERROR:
        raise click.ClickException(f"Update failed: {detail}")
    if status is UpdateStatus.UP_TO_DATE:
        click.echo(
            click.style(f"✅ Already up to date, v{current}.", fg="green"),
            err=True,
        )
        return

    click.echo(
        click.style(f"✅ grind has been updated to v{detail}.", fg="green"),
        err=True,
    )
    # The completion scripts re-invoke the binary, so they track it for free.
    # The man page is a static file and may sit somewhere needing privileges,
    # so point at the installer rather than trying to rewrite it here.
    click.echo(
        click.style(
            "   Re-run install.sh if you also want a refreshed man page.", fg="cyan"
        ),
        err=True,
    )
