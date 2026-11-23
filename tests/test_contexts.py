"""Working contexts, driven through the CLI with HTTP faked underneath."""

from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from grind.cli import main
from grind.contexts import (
    Context,
    ContextError,
    apply_context,
    load_contexts,
    read_active_context,
    write_active_context,
)

GH = "https://api.github.com"
JIRA = "https://acme.atlassian.net/rest/api/3"

SOURCES = """
[sources.oss]
provider = "github"
repo = "acme/beans"

[sources.work]
provider = "jira"
url = "https://acme.atlassian.net"
user = "ada@acme.example"
project = "PROJ"
"""

CONTEXTS = """
[contexts.grind]
source = "oss"
repos = ["mrsixw/grind"]

[contexts.mrsixw]
source = "oss"
org = "mrsixw"
mine = false

[contexts.platform]
source = "work"
projects = ["PLAT", "OPS"]

[contexts.split]
source = "oss"
repos = ["mrsixw/grind", "mrsixw/breakfast"]
"""

CONFIG = SOURCES + CONTEXTS


def gh_issue(number=7, repo="mrsixw/grind"):
    return {
        "number": number,
        "title": "Descale the espresso machine",
        "state": "open",
        "repository_url": f"{GH}/repos/{repo}",
        "html_url": f"https://github.com/{repo}/issues/{number}",
        "updated_at": "2026-11-01T09:00:00Z",
        "assignees": [],
        "labels": [],
    }


@pytest.fixture
def grind(tmp_path, monkeypatch, requests_mock):
    monkeypatch.setenv("GH_TOKEN", "gh-tok")
    monkeypatch.setenv("JIRA_TOKEN", "jira-tok")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("GRIND_CONTEXT", raising=False)
    requests_mock.get(f"{GH}/search/issues", json={"items": [gh_issue()]})
    requests_mock.get(f"{JIRA}/search/jql", json={"issues": []})
    cfg = tmp_path / "config.toml"

    def run(*args, config=CONFIG):
        cfg.write_text(config)
        base = ["--config", str(cfg), "--no-colour", "--no-update-check"]
        return CliRunner().invoke(main, base + list(args))

    return run


def sent(requests_mock, fragment, name):
    """A query parameter as sent, unlowered (requests-mock lowercases ``qs``)."""
    urls = [r.url for r in requests_mock.request_history if fragment in r.url]
    return [parse_qs(urlsplit(url).query)[name][0] for url in urls]


# ── Switching ──────────────────────────────────────────────────────────────


def test_switching_context_changes_what_list_shows_with_no_flags(grind, requests_mock):
    assert grind("context", "use", "grind").exit_code == 0
    result = grind("list")
    assert result.exit_code == 0, result.output
    # Only the context's source is searched, with the context's repo.
    assert sent(requests_mock, "search/issues", "q") == [
        "is:issue repo:mrsixw/grind assignee:@me state:open"
    ]
    assert sent(requests_mock, "search/jql", "jql") == []
    assert "(context grind)" in result.stderr


def test_the_active_context_survives_across_runs(grind, isolated_state):
    grind("context", "use", "platform")
    assert read_active_context() == "platform"
    assert grind("context").stdout.startswith("platform  (work: projects PLAT, OPS)")


def test_a_context_scope_replaces_the_sources_own(grind, requests_mock):
    """The source's repo is more specific than the context's org, but loses."""
    grind("--context", "mrsixw", "list")
    assert sent(requests_mock, "search/issues", "q") == [
        "is:issue org:mrsixw state:open"
    ]


def test_a_jira_context_searches_its_projects(grind, requests_mock):
    grind("--context", "platform", "list")
    assert sent(requests_mock, "search/jql", "jql") == [
        'project in ("PLAT", "OPS") AND assignee = currentUser() '
        "AND statusCategory != Done ORDER BY updated DESC"
    ]


def test_the_flag_and_env_var_pick_a_context_for_one_run(
    grind, requests_mock, monkeypatch
):
    grind("context", "use", "grind")
    grind("--context", "mrsixw", "list")
    monkeypatch.setenv("GRIND_CONTEXT", "mrsixw")
    grind("list")
    assert (
        sent(requests_mock, "search/issues", "q")
        == ["is:issue org:mrsixw state:open"] * 2
    )
    assert read_active_context() == "grind"


def test_command_flags_beat_the_context(grind, requests_mock):
    grind("--context", "mrsixw", "list", "--mine", "--in", "acme/milk")
    assert sent(requests_mock, "search/issues", "q") == [
        "is:issue repo:acme/milk assignee:@me state:open"
    ]


def test_another_source_sets_the_context_aside_and_says_so(grind, requests_mock):
    result = grind("--context", "grind", "list", "-s", "work")
    assert result.exit_code == 0, result.output
    assert sent(requests_mock, "search/issues", "q") == []
    assert sent(requests_mock, "search/jql", "jql")[0].startswith('project = "PROJ"')
    assert "Context 'grind' is for source 'oss', so it is set aside" in result.stderr


def test_clearing_the_context_lists_every_source_again(grind, requests_mock):
    grind("context", "use", "grind")
    assert grind("context", "use", "--none").exit_code == 0
    assert read_active_context() is None
    grind("list")
    assert sent(requests_mock, "search/issues", "q") == [
        "is:issue repo:acme/beans assignee:@me state:open"
    ]
    assert len(sent(requests_mock, "search/jql", "jql")) == 1


def test_context_list_marks_the_active_one(grind):
    grind("context", "use", "platform")
    rows = {
        line.split("|")[3].strip(): line.split("|")[2].strip()
        for line in grind("context", "list").stdout.splitlines()
        if line.startswith("|") and "CONTEXT" not in line
    }
    assert rows == {"grind": "", "mrsixw": "", "platform": "☕", "split": ""}


def test_without_emoji_the_context_commands_use_none(grind):
    use = grind("--no-emoji", "context", "use", "platform")
    assert use.stderr.startswith("Now working in 'platform'")
    rows = {
        line.split("|")[3].strip(): line.split("|")[2].strip()
        for line in grind("--no-emoji", "context", "list").stdout.splitlines()
        if line.startswith("|") and "CONTEXT" not in line
    }
    assert rows == {"grind": "", "mrsixw": "", "platform": "*", "split": ""}


def test_without_emoji_the_context_warnings_use_none(grind, requests_mock):
    flagged = grind("--no-emoji", "--context", "missing", "context", "list")
    assert flagged.stderr.startswith("Unknown context 'missing'")
    write_active_context("gone")
    stored = grind("--no-emoji", "list")
    assert "\nThe active context 'gone'" in "\n" + stored.stderr


# ── create ─────────────────────────────────────────────────────────────────


def test_create_files_into_the_contexts_only_repo(grind, requests_mock):
    requests_mock.post(f"{GH}/repos/mrsixw/grind/issues", json=gh_issue(8))
    result = grind("--context", "grind", "create", "-t", "Grind finer")
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "oss:mrsixw/grind#8"


def test_create_in_a_multi_repo_context_lists_the_choices(grind, requests_mock):
    result = grind("--context", "split", "create", "-t", "Grind finer")
    assert result.exit_code == 1
    assert "Choose from: mrsixw/grind, mrsixw/breakfast" in result.stderr
    assert not requests_mock.request_history


# ── Mistakes ───────────────────────────────────────────────────────────────


def test_an_unknown_context_on_the_flag_is_an_error(grind):
    result = grind("--context", "nope", "list")
    assert result.exit_code == 1
    assert "Unknown context 'nope'. Defined: grind, mrsixw, platform, split." in (
        result.stderr
    )


def test_using_an_unknown_context_is_refused_and_stores_nothing(grind):
    result = grind("context", "use", "nope")
    assert result.exit_code == 1
    assert read_active_context() is None


def test_a_context_removed_from_config_is_reported_not_silently_ignored(
    grind, requests_mock
):
    write_active_context("gone")
    result = grind("list")
    assert result.exit_code == 0, result.output
    assert "The active context 'gone' is no longer in your config" in result.stderr
    assert len(sent(requests_mock, "search/jql", "jql")) == 1  # every source


def test_a_context_naming_an_unknown_source_fails_clearly(grind):
    config = SOURCES + '[contexts.x]\nsource = "trello"\n'
    result = grind("context", "use", "x", config=config)
    assert result.exit_code == 1
    assert "Context 'x' is for source 'trello', which is not configured" in (
        result.stderr
    )
    assert read_active_context() is None


def test_a_key_the_provider_does_not_take_fails_clearly(grind):
    config = SOURCES + '[contexts.x]\nsource = "oss"\nprojects = ["PROJ"]\n'
    result = grind("--context", "x", "list", config=config)
    assert result.exit_code == 1
    assert "sets 'projects', which source 'oss' does not take" in result.stderr


@pytest.mark.parametrize("key", ["token-env", "url", "user", "provider"])
def test_a_context_cannot_carry_credentials_or_redefine_the_source(grind, key):
    config = SOURCES + f'[contexts.x]\nsource = "oss"\n{key} = "MINE"\n'
    result = grind("context", "use", "x", config=config)
    assert result.exit_code == 1
    assert f"Context 'x' sets '{key}', which source 'oss' does not take" in (
        result.stderr
    )
    assert read_active_context() is None


def test_a_jql_only_context_replaces_the_sources_project(grind, requests_mock):
    config = SOURCES + '[contexts.x]\nsource = "work"\njql = "labels = backend"\n'
    grind("--context", "x", "list", config=config)
    assert sent(requests_mock, "search/jql", "jql") == [
        "(labels = backend) AND assignee = currentUser() "
        "AND statusCategory != Done ORDER BY updated DESC"
    ]


@pytest.mark.parametrize(
    "args",
    [
        ("--context", "missing", "context", "use", "--none"),
        ("--context", "missing", "context", "use", "grind"),
        ("--context", "missing", "context", "list"),
    ],
)
def test_a_bad_context_flag_cannot_block_the_context_commands(grind, args):
    result = grind(*args)
    assert result.exit_code == 0, result.output
    assert "Unknown context 'missing'" in result.stderr


def test_context_use_needs_exactly_one_of_a_name_or_none(grind):
    assert grind("context", "use").exit_code == 2
    assert grind("context", "use", "grind", "--none").exit_code == 2


# ── The module ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ({"x": {"org": "a"}}, "needs a source"),
        ({"x": {"source": "oss", "mine": "no"}}, "mine must be true or false"),
        ({"x": "oss"}, "must be a table"),
    ],
)
def test_load_contexts_rejects_malformed_tables(table, message):
    with pytest.raises(ContextError, match=message):
        load_contexts({"contexts": table})


def test_apply_context_replaces_the_whole_scope_and_keeps_the_rest():
    context = Context("c", "work", {"projects": ["A"], "mine": False})
    merged = apply_context(
        context,
        {"url": "u", "project": "PROJ", "jql": "labels = x"},
        ("project", "projects", "jql"),
    )
    assert merged == {"url": "u", "projects": ["A"], "mine": False}


def test_a_plugin_scope_key_is_accepted_and_replaces_the_sources_own():
    context = Context("c", "desk", {"board": ["ops"]})
    merged = apply_context(
        context, {"board": ["dev"], "team": "a", "token-env": "T"}, ("board", "team")
    )
    assert merged == {"board": ["ops"], "token-env": "T"}
    assert context.describe() == "desk: board ops"


def test_apply_context_without_scope_keys_leaves_the_scope_alone():
    merged = apply_context(Context("c", "oss", {"mine": False}), {"repo": "a/b"}, ())
    assert merged == {"repo": "a/b", "mine": False}


def test_the_state_file_round_trips(isolated_state):
    write_active_context("grind")
    assert (isolated_state / "grind" / "context").read_text() == "grind\n"
    write_active_context(None)
    assert read_active_context() is None
    write_active_context(None)  # clearing twice is fine
