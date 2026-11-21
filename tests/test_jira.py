"""The JIRA provider is a stub: it can be configured, and says so when used."""

import pytest
from click.testing import CliRunner

from grind.cli import main

CONFIG = '[sources.work]\nprovider = "jira"\nurl = "https://acme.atlassian.net"\n'


@pytest.fixture
def grind(tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_TOKEN", "jira-tok")
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG)

    def run(*args):
        base = ["--config", str(cfg), "--no-colour", "--no-update-check"]
        return CliRunner().invoke(main, base + list(args))

    return run


def test_a_jira_source_is_listed_with_its_url(grind):
    result = grind("sources")
    assert result.exit_code == 0, result.output
    assert "jira" in result.stdout
    assert "https://acme.atlassian.net" in result.stdout


@pytest.mark.parametrize(
    ("args", "what"),
    [
        (("list",), "listing tickets"),
        (("show", "work:PROJ-1"), "showing tickets"),
        (("create", "-t", "T"), "creating tickets"),
        (("edit", "work:PROJ-1", "-t", "T"), "editing tickets"),
        (("comment", "work:PROJ-1", "hi"), "commenting"),
        (("assign", "work:PROJ-1"), "assigning tickets"),
        (("move", "work:PROJ-1", "closed"), "moving tickets between statuses"),
        (("sources", "--check"), "identifying the current user"),
    ],
)
def test_every_operation_says_it_is_a_stub(grind, requests_mock, args, what):
    result = grind(*args)
    assert result.exit_code == 1
    assert (
        f"The 'jira' provider (source 'work') cannot do {what} yet: it is a stub."
        in result.output
    )
    assert requests_mock.call_count == 0


def test_a_jira_source_needs_a_url(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[sources.work]\nprovider = "jira"\n')
    result = CliRunner().invoke(
        main, ["--config", str(cfg), "--no-colour", "--no-update-check", "list"]
    )
    assert result.exit_code == 1
    assert "Source 'work' is missing 'url'" in result.stderr
