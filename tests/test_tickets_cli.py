"""The ticket commands, driven through Click with HTTP faked underneath.

These go through the built-in GitHub and JIRA providers. The same commands
against a plugin are in ``test_plugin_cli.py``.
"""

import json

import pytest
from click.testing import CliRunner
from freezegun import freeze_time
from wcwidth import wcswidth

from grind.cli import main
from grind.constants import TABLE_STYLES
from grind.jira import text_to_adf

GH = "https://api.github.com"
JIRA = "https://acme.atlassian.net/rest/api/3"
#: A date no seasonal calendar marks, so the theme alone decides the colours.
PLAIN_DAY = "2026-11-15"

CONFIG = """
[sources.oss]
provider = "github"
repo = "acme/beans"

[sources.work]
provider = "jira"
url = "https://acme.atlassian.net"
user = "ada@acme.example"
project = "PROJ"
"""


def gh_issue(number=7, **overrides):
    return {
        "number": number,
        "title": "Descale the espresso machine",
        "state": "open",
        "repository_url": f"{GH}/repos/acme/beans",
        "html_url": f"https://github.com/acme/beans/issues/{number}",
        "updated_at": "2026-11-01T09:00:00Z",
        "created_at": "2026-10-01T09:00:00Z",
        "user": {"login": "grace"},
        "assignees": [{"login": "ada"}],
        "labels": [{"name": "chore"}],
        "body": "It is furring up.",
        **overrides,
    }


def jira_issue(key="PROJ-1", **fields):
    return {
        "key": key,
        "fields": {
            "summary": "Order more beans",
            "status": {"name": "To Do", "statusCategory": {"key": "new"}},
            "issuetype": {"name": "Task"},
            "assignee": {"displayName": "Ada Lovelace"},
            "labels": [],
            "updated": "2026-11-05T09:00:00.000+0000",
            "description": text_to_adf("Nearly out."),
            **fields,
        },
    }


@pytest.fixture
def grind(tmp_path, monkeypatch):
    """Invoke grind against a two-source config, quietly and without colour."""
    monkeypatch.setenv("GH_TOKEN", "gh-tok")
    monkeypatch.setenv("JIRA_TOKEN", "jira-tok")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG)

    def run(*args, config=CONFIG, **kwargs):
        cfg.write_text(config)
        base = ["--config", str(cfg), "--no-colour", "--no-update-check"]
        return CliRunner().invoke(main, base + list(args), **kwargs)

    return run


@pytest.fixture
def both(requests_mock):
    requests_mock.get(f"{GH}/search/issues", json={"items": [gh_issue()]})
    requests_mock.get(f"{JIRA}/search/jql", json={"issues": [jira_issue()]})
    return requests_mock


# ── list ───────────────────────────────────────────────────────────────────


def cells(line):
    """Split one outline-table row into its stripped cell texts."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def table_rows(stdout):
    """Return the header and body rows of an outline table, borders dropped."""
    return [cells(line) for line in stdout.splitlines() if line.startswith("|")]


def test_list_merges_sources_newest_first(grind, both):
    result = grind("list")
    assert result.exit_code == 0, result.output
    header, first, second = table_rows(result.stdout)
    assert header == ["", "TICKET", "STATUS", "ASSIGNEE", "UPDATED", "TITLE"]
    assert first[:2] == ["0", "work:PROJ-1"]
    assert second[:2] == ["1", "oss:acme/beans#7"]
    assert first[-1] == "Order more beans"
    assert "Grinding through your tickets" in result.stderr
    assert "Grinding" not in result.stdout


def test_list_draws_an_outline_table_by_default(grind, both):
    lines = grind("list").stdout.splitlines()
    assert lines[0].startswith("+-") and lines[2].startswith("+=")
    assert lines[-1].startswith("+-")


@pytest.mark.parametrize("style", TABLE_STYLES)
def test_every_table_style_renders_the_tickets(grind, both, style):
    result = grind("--table-style", style, "list")
    assert result.exit_code == 0, result.output
    assert "work:PROJ-1" in result.stdout and "oss:acme/beans#7" in result.stdout


def test_table_style_comes_from_the_config_file(grind, both):
    result = grind("list", config='table-style = "simple"\n' + CONFIG)
    assert result.exit_code == 0, result.output
    assert not result.stdout.startswith("+")
    assert result.stdout.splitlines()[1].startswith("--")


def test_the_flag_beats_the_config_file_table_style(grind, both):
    result = grind(
        "--table-style", "grid", "list", config='table-style = "simple"\n' + CONFIG
    )
    assert result.stdout.startswith("+-")


def test_an_unknown_table_style_in_config_lists_the_choices(grind, both):
    result = grind("list", config='table-style = "fancy"\n' + CONFIG)
    assert result.exit_code == 1
    assert "Invalid table-style 'fancy'" in result.stderr
    assert ", ".join(TABLE_STYLES) in result.stderr


@pytest.mark.parametrize("style", TABLE_STYLES)
def test_list_clips_titles_to_fit_the_terminal(
    grind, requests_mock, monkeypatch, style
):
    long_title = "Descale the espresso machine before it seizes up " * 3
    requests_mock.get(
        f"{GH}/search/issues", json={"items": [gh_issue(title=long_title)]}
    )
    requests_mock.get(f"{JIRA}/search/jql", json={"issues": []})
    width = 100
    monkeypatch.setenv("COLUMNS", str(width))
    stdout = grind("--table-style", style, "list").stdout
    assert max(len(line) for line in stdout.splitlines()) == width
    assert "…" in stdout and long_title.strip() not in stdout


def test_titles_keep_a_readable_minimum_in_a_tiny_terminal(
    grind, requests_mock, monkeypatch
):
    """Below the minimum the table overflows rather than hiding the title."""
    requests_mock.get(
        f"{GH}/search/issues", json={"items": [gh_issue(title="x" * 100)]}
    )
    requests_mock.get(f"{JIRA}/search/jql", json={"issues": []})
    monkeypatch.setenv("COLUMNS", "40")
    title = table_rows(grind("list").stdout)[1][-1]
    assert title == "x" * 19 + "…"


def test_list_clips_wide_characters_by_their_terminal_width(
    grind, requests_mock, monkeypatch
):
    requests_mock.get(
        f"{GH}/search/issues", json={"items": [gh_issue(title="☕" * 80)]}
    )
    requests_mock.get(f"{JIRA}/search/jql", json={"issues": []})
    width = 100
    monkeypatch.setenv("COLUMNS", str(width))
    lines = grind("list").stdout.splitlines()
    assert max(wcswidth(line) for line in lines) <= width


def test_list_json_is_pure_json_on_stdout(grind, both):
    result = grind("list", "--format", "json")
    payload = json.loads(result.stdout)
    assert [t["ref"] for t in payload] == ["work:PROJ-1", "oss:acme/beans#7"]
    assert payload[1]["labels"] == ["chore"]
    assert payload[0]["is_open"] is True


def test_list_format_and_limit_come_from_the_config_file(grind, both):
    result = grind("list", config='format = "json"\nlimit = 5\n' + CONFIG)
    assert json.loads(result.stdout)
    assert both.request_history[0].qs["per_page"] == ["5"]


def test_list_can_be_narrowed_to_one_source(grind, both):
    result = grind("list", "--source", "work")
    assert "work:PROJ-1" in result.stdout
    assert "oss:" not in result.stdout
    assert both.call_count == 1


def test_list_unknown_source_is_an_error(grind, both):
    result = grind("list", "-s", "nope")
    assert result.exit_code == 1
    assert "Unknown source 'nope'. Configured: oss, work." in result.stderr
    assert both.call_count == 0


def test_list_passes_filters_through(grind, both):
    grind("list", "--all", "--state", "closed", "-q", "kettle", "--in", "acme/milk")
    github_q = both.request_history[0].qs["q"][0]
    assert github_q == "is:issue repo:acme/milk state:closed kettle"


def test_list_empty_says_so_on_stderr_and_leaves_stdout_empty(grind, requests_mock):
    requests_mock.get(f"{GH}/search/issues", json={"items": []})
    result = grind("list", "-s", "oss")
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "Nothing to grind" in result.stderr


def test_list_empty_json_is_still_valid_json(grind, requests_mock):
    requests_mock.get(f"{GH}/search/issues", json={"items": []})
    result = grind("list", "-s", "oss", "--format", "json")
    assert json.loads(result.stdout) == []


def test_one_failing_source_does_not_hide_the_others(grind, requests_mock):
    requests_mock.get(f"{GH}/search/issues", json={"items": [gh_issue()]})
    requests_mock.get(f"{JIRA}/search/jql", status_code=401)
    result = grind("list")
    assert result.exit_code == 1
    assert "oss:acme/beans#7" in result.stdout
    assert "Source 'work' answered 401" in result.stderr


def test_long_titles_are_clipped_to_the_terminal(grind, requests_mock):
    requests_mock.get(
        f"{GH}/search/issues", json={"items": [gh_issue(title="x" * 500)]}
    )
    result = grind("list", "-s", "oss")
    assert max(len(line) for line in result.stdout.splitlines()) <= 120
    assert "…" in result.stdout


def test_debug_summary_counts_requests_per_source(grind, both):
    result = grind("--debug-summary", "list")
    assert "Requests to oss:" in result.stderr
    assert "Requests to work:" in result.stderr
    assert "Items processed:  2" in result.stderr


# ── cache ──────────────────────────────────────────────────────────────────


def test_cache_serves_the_second_list_without_a_request(grind, both):
    first = grind("--cache", "list")
    second = grind("--cache", "list")
    assert both.call_count == 2  # one per source, first run only
    assert second.stdout == first.stdout


def test_no_cache_always_asks(grind, both):
    grind("list")
    grind("list")
    assert both.call_count == 4


def test_cache_is_keyed_on_the_query(grind, both):
    grind("--cache", "list", "-s", "oss")
    grind("--cache", "list", "-s", "oss", "--state", "closed")
    assert both.call_count == 2


def test_cache_is_keyed_on_the_source_config(grind, both):
    grind("--cache", "list", "-s", "oss")
    grind("--cache", "list", "-s", "oss", config=CONFIG.replace("beans", "milk"))
    assert both.call_count == 2


# ── show ───────────────────────────────────────────────────────────────────


def test_show_renders_the_ticket(grind, requests_mock):
    requests_mock.get(f"{GH}/repos/acme/beans/issues/7", json=gh_issue())
    result = grind("show", "oss:#7")
    assert result.exit_code == 0, result.output
    assert "oss:acme/beans#7  Descale the espresso machine" in result.stdout
    assert "Assignee: ada" in result.stdout
    assert "Labels:   chore" in result.stdout
    assert "It is furring up." in result.stdout


def test_show_aligns_its_values_in_plain_output(grind, requests_mock):
    requests_mock.get(f"{GH}/repos/acme/beans/issues/7", json=gh_issue())
    lines = grind("show", "oss:#7").stdout.splitlines()
    assert "  Status:   open" in lines
    assert "  Reporter: grace" in lines
    assert "\x1b[" not in "\n".join(lines)


@pytest.mark.parametrize(
    ("theme", "label", "value"),
    [
        ("default", "\x1b[38;5;173m", "\x1b[38;5;180m"),  # caramel, latte
        ("dark", "\x1b[95m", "\x1b[97m"),  # bright magenta, bright white
    ],
)
def test_show_colours_labels_and_values_from_the_theme(
    tmp_path, monkeypatch, requests_mock, theme, label, value
):
    requests_mock.get(f"{GH}/repos/acme/beans/issues/7", json=gh_issue())
    result = run_in_colour(tmp_path, monkeypatch, "--theme", theme, "show", "oss:#7")
    assert result.exit_code == 0, result.output
    status = next(line for line in result.stdout.splitlines() if "Status:" in line)
    assert status.startswith(f"  \x1b[1m{label}Status:")
    assert f"{value}open" in status


def test_show_comments_and_json(grind, requests_mock):
    with_comment = jira_issue(
        comment={
            "comments": [
                {"author": {"displayName": "Grace"}, "body": text_to_adf("Ordered.")}
            ]
        }
    )
    requests_mock.get(f"{JIRA}/issue/PROJ-1", json=with_comment)
    text = grind("show", "work:PROJ-1", "--comments")
    assert "💬 Grace" in text.stdout
    assert "Ordered." in text.stdout
    as_json = grind("show", "work:PROJ-1", "--comments", "--format", "json")
    assert json.loads(as_json.stdout)["comments"][0]["body"] == "Ordered."


def test_show_ambiguous_ref_asks_for_a_source(grind, requests_mock):
    result = grind("show", "PROJ-1")
    assert result.exit_code == 1
    assert "<source>:<key>" in result.stderr
    assert requests_mock.call_count == 0


def test_show_not_found_is_a_clean_error(grind, requests_mock):
    requests_mock.get(f"{JIRA}/issue/PROJ-404", status_code=404)
    result = grind("show", "work:PROJ-404")
    assert result.exit_code == 1
    assert "answered 404" in result.stderr
    assert result.stdout == ""


# ── create ─────────────────────────────────────────────────────────────────


def test_create_prints_only_the_ref_on_stdout(grind, requests_mock):
    requests_mock.post(f"{GH}/repos/acme/beans/issues", json=gh_issue(8))
    result = grind("create", "-s", "oss", "-t", "Buy filters", "-l", "shop")
    assert result.exit_code == 0, result.output
    assert result.stdout == "oss:acme/beans#8\n"
    assert "Freshly ground" in result.stderr
    assert requests_mock.last_request.json() == {
        "title": "Buy filters",
        "body": "",
        "labels": ["shop"],
    }


def test_create_reads_the_body_from_stdin(grind, requests_mock):
    requests_mock.post(f"{JIRA}/issue", json={"key": "PROJ-9"})
    requests_mock.get(f"{JIRA}/issue/PROJ-9", json=jira_issue("PROJ-9"))
    result = grind(
        "create",
        "-s",
        "work",
        "-t",
        "T",
        "--type",
        "Bug",
        "--body-file",
        "-",
        input="from stdin",
    )
    assert result.stdout == "work:PROJ-9\n"
    posted = next(r for r in requests_mock.request_history if r.method == "POST")
    assert posted.json()["fields"]["description"] == text_to_adf("from stdin")
    assert posted.json()["fields"]["issuetype"] == {"name": "Bug"}


def test_create_needs_a_source_when_several_are_configured(grind, requests_mock):
    result = grind("create", "-t", "T")
    assert result.exit_code == 1
    assert "Which source? Pass --source. Configured: oss, work." in result.stderr
    assert requests_mock.call_count == 0


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


def test_edit_sends_the_changes(grind, requests_mock):
    requests_mock.put(f"{JIRA}/issue/PROJ-1", status_code=204)
    requests_mock.get(f"{JIRA}/issue/PROJ-1", json=jira_issue())
    result = grind("edit", "work:PROJ-1", "-t", "New", "--add-label", "urgent")
    assert result.exit_code == 0, result.output
    assert result.stdout == "work:PROJ-1\n"
    assert "Updated work:PROJ-1" in result.stderr
    put = next(r for r in requests_mock.request_history if r.method == "PUT")
    assert put.json() == {
        "fields": {"summary": "New"},
        "update": {"labels": [{"add": "urgent"}]},
    }


def test_edit_with_nothing_to_change_is_a_usage_error(grind, requests_mock):
    result = grind("edit", "work:PROJ-1")
    assert result.exit_code == 2
    assert "Nothing to change" in result.stderr
    assert requests_mock.call_count == 0


def test_comment(grind, requests_mock):
    requests_mock.post(
        f"{GH}/repos/acme/beans/issues/7/comments", json={"body": "Done."}
    )
    result = grind("comment", "oss:#7", "Done.")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Comment added to oss:#7" in result.stderr
    assert requests_mock.last_request.json() == {"body": "Done."}


def test_empty_comment_is_refused(grind, requests_mock):
    result = grind("comment", "oss:#7", "   ")
    assert result.exit_code == 2
    assert requests_mock.call_count == 0


def test_assign_defaults_to_me(grind, requests_mock):
    requests_mock.get(f"{GH}/user", json={"login": "ada"})
    requests_mock.patch(f"{GH}/repos/acme/beans/issues/7", json=gh_issue())
    result = grind("assign", "oss:#7")
    assert result.exit_code == 0, result.output
    assert requests_mock.last_request.json() == {"assignees": ["ada"]}
    assert "now assigned to ada" in result.stderr


def test_assign_nobody(grind, requests_mock):
    requests_mock.patch(f"{GH}/repos/acme/beans/issues/7", json=gh_issue(assignees=[]))
    result = grind("assign", "oss:#7", "--nobody")
    assert requests_mock.last_request.json() == {"assignees": []}
    assert "now assigned to nobody" in result.stderr


def test_assign_user_and_nobody_conflict(grind):
    assert grind("assign", "oss:#7", "grace", "--nobody").exit_code == 2


def test_move(grind, requests_mock):
    requests_mock.patch(
        f"{GH}/repos/acme/beans/issues/7", json=gh_issue(state="closed")
    )
    result = grind("move", "oss:#7", "done")
    assert result.exit_code == 0, result.output
    assert result.stdout == "oss:acme/beans#7\n"
    assert "is now closed" in result.stderr


def test_move_to_an_impossible_status_is_a_clean_error(grind, requests_mock):
    result = grind("move", "oss:#7", "In Progress")
    assert result.exit_code == 1
    assert "open, closed, not-planned" in result.stderr


# ── sources ────────────────────────────────────────────────────────────────


def test_sources_lists_sources_and_providers(grind):
    result = grind("sources")
    assert result.exit_code == 0, result.output
    assert "oss" in result.stdout and "https://api.github.com" in result.stdout
    assert "work" in result.stdout and "https://acme.atlassian.net" in result.stdout
    assert "built-in" in result.stdout


def test_sources_check_reports_each_source_and_fails_if_any_does(grind, requests_mock):
    requests_mock.get(f"{GH}/user", json={"login": "ada"})
    requests_mock.get(f"{JIRA}/myself", status_code=401)
    result = grind("sources", "--check")
    assert result.exit_code == 1
    assert "✅ ada" in result.stdout
    assert "❌ Source 'work' answered 401" in result.stdout


def test_sources_plugin_dir(grind, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    result = grind("sources", "--plugin-dir")
    assert result.stdout.strip() == str(tmp_path / "grind" / "plugins")


def test_a_bad_source_config_is_a_clean_error(grind):
    result = grind("list", config='[sources.x]\nprovider = "trello"\n')
    assert result.exit_code == 1
    assert "Unknown provider 'trello'" in result.stderr


def run_in_colour(tmp_path, monkeypatch, *args):
    """Invoke grind with colour on, on a day no seasonal calendar marks."""
    monkeypatch.setenv("GH_TOKEN", "gh-tok")
    monkeypatch.setenv("JIRA_TOKEN", "jira-tok")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("GRIND_NO_COLOUR", raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG)
    with freeze_time(PLAIN_DAY):
        return CliRunner().invoke(
            main, ["--config", str(cfg), "--no-update-check", *args], color=True
        )


@pytest.mark.usefixtures("both")
def test_list_is_coffee_coloured_by_default(tmp_path, monkeypatch):
    """The table, its header and the progress line all wear the coffee theme."""
    result = run_in_colour(tmp_path, monkeypatch, "list")
    assert result.exit_code == 0, result.output
    top, header, rule, *rows, bottom = result.stdout.splitlines()
    for border in (top, rule, bottom):
        assert border.startswith("\x1b[38;5;180m")  # latte
    assert "\x1b[38;5;173m" in header  # caramel
    assert all(row.startswith("\x1b[38;5;137m") for row in rows)  # mocha
    assert "\x1b[36m" not in result.output  # no leftover template cyan


def test_tokens_never_reach_the_output(grind, both):
    result = grind("--debug-summary", "list", "--format", "json")
    assert "gh-tok" not in result.output
    assert "jira-tok" not in result.output
