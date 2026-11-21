"""The ticket commands, driven through Click against an in-memory plugin.

The pantry provider (``tests/pantry.py``) is installed as a real plugin,
through a ``grind.providers`` entry point, so these tests cover the CLI's side
of the plugin API: that it finds a plugin, which calls it makes, with what,
and what it prints, using nothing a built-in provider has that a plugin
lacks. ``test_tickets_cli.py`` runs the same commands through the built-in
providers with HTTP faked.
"""

import json

import pytest
from click.testing import CliRunner
from freezegun import freeze_time

from grind.cli import main
from grind.tickets import ME, Comment, Ticket, TicketChanges
from tests.pantry import pantry_fixture  # noqa: F401  (the pantry fixture)

CONFIG = """
[sources.oss]
provider = "pantry"

[sources.work]
provider = "pantry"
"""

BEANS = Ticket(
    source="oss",
    key="acme/beans#7",
    title="Descale the espresso machine",
    status="open",
    assignee="ada",
    reporter="grace",
    labels=("chore",),
    url="https://pantry.example/oss/7",
    created="2026-10-01T09:00:00Z",
    updated="2026-11-01T09:00:00Z",
    body="It is furring up.",
)
ORDER = Ticket(
    source="work",
    key="PROJ-1",
    title="Order more beans",
    status="To Do",
    type="Task",
    assignee="Ada Lovelace",
    updated="2026-11-05T09:00:00.000+0000",
    body="Nearly out.",
    comments=(Comment(author="Grace", body="Ordered."),),
)


@pytest.fixture
def grind(tmp_path, monkeypatch, pantry):
    """Invoke grind against a two-source config, quietly and without colour."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cfg = tmp_path / "config.toml"

    def run(*args, config=CONFIG, **kwargs):
        cfg.write_text(config)
        base = ["--config", str(cfg), "--no-colour", "--no-update-check"]
        return CliRunner().invoke(main, base + list(args), **kwargs)

    return run


@pytest.fixture
def stocked(pantry):
    pantry.add(BEANS, ORDER)
    return pantry


# ── list ───────────────────────────────────────────────────────────────────


def cells(line):
    """Split one outline-table row into its stripped cell texts."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def table_rows(stdout):
    """Return the header and body rows of an outline table, borders dropped."""
    return [cells(line) for line in stdout.splitlines() if line.startswith("|")]


def test_list_merges_sources_newest_first(grind, stocked):
    result = grind("list")
    assert result.exit_code == 0, result.output
    header, first, second = table_rows(result.stdout)
    assert header == ["", "TICKET", "STATUS", "ASSIGNEE", "UPDATED", "TITLE"]
    assert first[:2] == ["0", "work:PROJ-1"]
    assert second[:2] == ["1", "oss:acme/beans#7"]
    assert first[-1] == "Order more beans"
    assert (
        "Grinding through open tickets assigned to you in oss, work..." in result.stderr
    )
    assert "Grinding" not in result.stdout


def test_list_json_is_pure_json_on_stdout(grind, stocked):
    result = grind("list", "--format", "json")
    payload = json.loads(result.stdout)
    assert [t["ref"] for t in payload] == ["work:PROJ-1", "oss:acme/beans#7"]
    assert payload[1]["labels"] == ["chore"]
    assert payload[0]["is_open"] is True


def test_list_format_and_limit_come_from_the_config_file(grind, stocked):
    result = grind("list", config='format = "json"\nlimit = 5\n' + CONFIG)
    assert json.loads(result.stdout)
    assert {query.limit for query in stocked.made("list")} == {5}


def test_list_can_be_narrowed_to_one_source(grind, stocked):
    result = grind("list", "--source", "work")
    assert "work:PROJ-1" in result.stdout
    assert "oss:" not in result.stdout
    assert [src for src, _, _ in stocked.calls] == ["work"]


def test_list_unknown_source_is_an_error(grind, stocked):
    result = grind("list", "-s", "nope")
    assert result.exit_code == 1
    assert "Unknown source 'nope'. Configured: oss, work." in result.stderr
    assert stocked.calls == []


def test_list_passes_filters_through(grind, stocked):
    grind("list", "--all", "--state", "closed", "-q", "kettle", "--in", "acme/milk")
    (query,) = stocked.made("list", "oss")
    assert (query.mine, query.state, query.text, query.containers) == (
        False,
        "closed",
        "kettle",
        ("acme/milk",),
    )


def test_list_asks_for_your_open_tickets_by_default(grind, stocked):
    grind("list", "-s", "oss")
    (query,) = stocked.made("list")
    assert (query.mine, query.state, query.text, query.containers) == (
        True,
        "open",
        "",
        (),
    )


def test_list_empty_says_so_on_stderr_and_leaves_stdout_empty(grind, pantry):
    result = grind("list", "-s", "oss")
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "Nothing to grind" in result.stderr


def test_list_empty_json_is_still_valid_json(grind, pantry):
    result = grind("list", "-s", "oss", "--format", "json")
    assert json.loads(result.stdout) == []


def test_one_failing_source_does_not_hide_the_others(grind, stocked):
    stocked.failures["work"] = "The work pantry is locked."
    result = grind("list")
    assert result.exit_code == 1
    assert "oss:acme/beans#7" in result.stdout
    assert "The work pantry is locked." in result.stderr


def test_long_titles_are_clipped_to_the_terminal(grind, pantry):
    pantry.add(Ticket(source="oss", key="1", title="x" * 500, status="open"))
    result = grind("list", "-s", "oss")
    assert max(len(line) for line in result.stdout.splitlines()) <= 120
    assert "…" in result.stdout


def test_debug_summary_counts_requests_per_source(grind, stocked):
    result = grind("--debug-summary", "list")
    assert "Requests to oss:" in result.stderr
    assert "Requests to work:" in result.stderr
    assert "Items processed:  2" in result.stderr


# ── cache ──────────────────────────────────────────────────────────────────


def test_cache_serves_the_second_list_without_a_request(grind, stocked):
    first = grind("--cache", "list")
    second = grind("--cache", "list")
    assert len(stocked.made("list")) == 2  # one per source, first run only
    assert second.stdout == first.stdout


def test_no_cache_always_asks(grind, stocked):
    grind("list")
    grind("list")
    assert len(stocked.made("list")) == 4


def test_cache_is_keyed_on_the_query(grind, stocked):
    grind("--cache", "list", "-s", "oss")
    grind("--cache", "list", "-s", "oss", "--state", "closed")
    assert len(stocked.made("list")) == 2


def test_cache_is_keyed_on_the_source_config(grind, stocked):
    grind("--cache", "list", "-s", "oss")
    changed = CONFIG.replace(
        '[sources.oss]\nprovider = "pantry"\n',
        '[sources.oss]\nprovider = "pantry"\nshelf = "b"\n',
    )
    grind("--cache", "list", "-s", "oss", config=changed)
    assert len(stocked.made("list")) == 2


# ── show ───────────────────────────────────────────────────────────────────


def test_show_renders_the_ticket(grind, stocked):
    result = grind("show", "oss:acme/beans#7")
    assert result.exit_code == 0, result.output
    assert "oss:acme/beans#7  Descale the espresso machine" in result.stdout
    assert "Assignee: ada" in result.stdout
    assert "Labels:   chore" in result.stdout
    assert "It is furring up." in result.stdout
    assert stocked.made("get") == ["acme/beans#7"]


def test_show_comments_and_json(grind, stocked):
    plain = grind("show", "work:PROJ-1")
    assert "Ordered." not in plain.stdout
    text = grind("show", "work:PROJ-1", "--comments")
    assert "💬 Grace" in text.stdout
    assert "Ordered." in text.stdout
    as_json = grind("show", "work:PROJ-1", "--comments", "--format", "json")
    assert json.loads(as_json.stdout)["comments"][0]["body"] == "Ordered."


def test_show_ambiguous_ref_asks_for_a_source(grind, stocked):
    result = grind("show", "PROJ-1")
    assert result.exit_code == 1
    assert "<source>:<key>" in result.stderr
    assert stocked.calls == []


def test_show_prefix_is_optional_with_one_source(grind, stocked):
    result = grind("show", "PROJ-1", config='[sources.work]\nprovider = "pantry"\n')
    assert result.exit_code == 0, result.output
    assert "work:PROJ-1" in result.stdout


def test_show_not_found_is_a_clean_error(grind, stocked):
    result = grind("show", "work:PROJ-404")
    assert result.exit_code == 1
    assert "Source 'work' has no ticket PROJ-404." in result.stderr
    assert result.stdout == ""


# ── create ─────────────────────────────────────────────────────────────────


def test_create_prints_only_the_ref_on_stdout(grind, pantry):
    result = grind("create", "-s", "oss", "-t", "Buy filters", "-l", "shop")
    assert result.exit_code == 0, result.output
    assert result.stdout == "oss:1\n"
    assert "Freshly ground" in result.stderr
    (draft,) = pantry.made("create")
    assert (draft.title, draft.body, draft.labels) == ("Buy filters", "", ("shop",))


def test_create_passes_type_container_and_assignee(grind, pantry):
    grind("create", "-s", "work", "-t", "T", "--type", "Bug", "--in", "OPS", "-a", ME)
    (draft,) = pantry.made("create")
    assert (draft.type, draft.container, draft.assignee) == ("Bug", "OPS", ME)


def test_create_reads_the_body_from_stdin(grind, pantry):
    result = grind(
        "create", "-s", "work", "-t", "T", "--body-file", "-", input="from stdin"
    )
    assert result.stdout == "work:1\n"
    (draft,) = pantry.made("create")
    assert draft.body == "from stdin"


def test_create_needs_a_source_when_several_are_configured(grind, pantry):
    result = grind("create", "-t", "T")
    assert result.exit_code == 1
    assert "Which source? Pass --source. Configured: oss, work." in result.stderr
    assert pantry.calls == []


def test_create_needs_a_title(grind):
    result = grind("create", "-s", "oss")
    assert result.exit_code == 2
    assert "--title" in result.stderr


def test_body_and_body_file_together_is_a_usage_error(grind, tmp_path):
    body = tmp_path / "b.txt"
    body.write_text("x")
    result = grind(
        "create", "-s", "oss", "-t", "T", "-b", "x", "--body-file", str(body)
    )
    assert result.exit_code == 2
    assert "not both" in result.stderr


# ── edit, comment, assign, move ────────────────────────────────────────────


def test_edit_sends_the_changes(grind, stocked):
    result = grind("edit", "work:PROJ-1", "-t", "New", "--add-label", "urgent")
    assert result.exit_code == 0, result.output
    assert result.stdout == "work:PROJ-1\n"
    assert "Updated work:PROJ-1" in result.stderr
    assert stocked.made("update") == [
        ("PROJ-1", TicketChanges(title="New", add_labels=("urgent",)))
    ]


def test_edit_with_nothing_to_change_is_a_usage_error(grind, stocked):
    result = grind("edit", "work:PROJ-1")
    assert result.exit_code == 2
    assert "Nothing to change" in result.stderr
    assert stocked.calls == []


def test_comment(grind, stocked):
    result = grind("comment", "oss:acme/beans#7", "Done.")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Comment added to oss:acme/beans#7" in result.stderr
    assert stocked.made("comment") == [("acme/beans#7", "Done.")]


def test_empty_comment_is_refused(grind, stocked):
    result = grind("comment", "oss:acme/beans#7", "   ")
    assert result.exit_code == 2
    assert stocked.calls == []


def test_assign_defaults_to_me(grind, stocked):
    result = grind("assign", "oss:acme/beans#7")
    assert result.exit_code == 0, result.output
    assert stocked.made("assign") == [("acme/beans#7", ME)]
    assert "now assigned to ada" in result.stderr


def test_assign_nobody(grind, stocked):
    result = grind("assign", "oss:acme/beans#7", "--nobody")
    assert stocked.made("assign") == [("acme/beans#7", None)]
    assert "now assigned to nobody" in result.stderr


def test_assign_user_and_nobody_conflict(grind):
    assert grind("assign", "oss:#7", "grace", "--nobody").exit_code == 2


def test_move(grind, stocked):
    result = grind("move", "oss:acme/beans#7", "closed")
    assert result.exit_code == 0, result.output
    assert result.stdout == "oss:acme/beans#7\n"
    assert "is now closed" in result.stderr
    assert stocked.made("move") == [("acme/beans#7", "closed")]


def test_move_to_an_impossible_status_is_a_clean_error(grind, stocked):
    result = grind("move", "oss:acme/beans#7", "In Progress")
    assert result.exit_code == 1
    assert "Available: open, closed." in result.stderr


# ── sources ────────────────────────────────────────────────────────────────


def test_sources_lists_sources_and_providers(grind):
    result = grind("sources")
    assert result.exit_code == 0, result.output
    assert "oss" in result.stdout and "work" in result.stdout
    assert "plugin (tests.pantry:Pantry)" in result.stdout
    assert "github" in result.stdout and "built-in" in result.stdout


def test_sources_check_reports_each_source_and_fails_if_any_does(grind, pantry):
    pantry.failures["work"] = "The work pantry is locked."
    result = grind("sources", "--check")
    assert result.exit_code == 1
    assert "✅ ada" in result.stdout
    assert "❌ The work pantry is locked." in result.stdout


def test_sources_plugin_dir(grind, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    result = grind("sources", "--plugin-dir")
    assert result.stdout.strip() == str(tmp_path / "grind" / "plugins")


def test_a_bad_source_config_is_a_clean_error(grind):
    result = grind("list", config='[sources.x]\nprovider = "trello"\n')
    assert result.exit_code == 1
    assert "Unknown provider 'trello'" in result.stderr


def test_list_is_coffee_coloured_by_default(tmp_path, monkeypatch, stocked):
    """The table, its header and the progress line all wear the coffee theme."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("GRIND_NO_COLOUR", raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG)
    with freeze_time("2026-11-15"):
        result = CliRunner().invoke(
            main, ["--config", str(cfg), "--no-update-check", "list"], color=True
        )
    assert result.exit_code == 0, result.output
    top, header, rule, *rows, bottom = result.stdout.splitlines()
    for border in (top, rule, bottom):
        assert border.startswith("\x1b[38;5;180m")  # latte
    assert "\x1b[38;5;173m" in header  # caramel
    assert all(row.startswith("\x1b[38;5;137m") for row in rows)  # mocha
    assert "\x1b[36m" not in result.output  # no leftover template cyan
