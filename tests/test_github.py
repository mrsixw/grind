"""The GitHub provider is a stub: it can be configured, and says so when used."""

import pytest
from click.testing import CliRunner

from grind.cli import main

CONFIG = '[sources.oss]\nprovider = "github"\nrepo = "acme/beans"\n'


@pytest.fixture
def grind(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "gh-tok")
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG)

    def run(*args):
        base = ["--config", str(cfg), "--no-colour", "--no-update-check"]
        return CliRunner().invoke(main, base + list(args))

    return run


def test_a_github_source_is_listed_with_its_default_url(grind):
    result = grind("sources")
    assert result.exit_code == 0, result.output
    assert "github" in result.stdout
    assert "https://api.github.com" in result.stdout


@pytest.mark.parametrize(
    ("args", "what"),
    [
        (("list",), "listing tickets"),
        (("show", "oss:#7"), "showing tickets"),
        (("create", "-t", "T"), "creating tickets"),
        (("edit", "oss:#7", "-t", "T"), "editing tickets"),
        (("comment", "oss:#7", "hi"), "commenting"),
        (("assign", "oss:#7"), "assigning tickets"),
        (("move", "oss:#7", "closed"), "moving tickets between statuses"),
        (("sources", "--check"), "identifying the current user"),
    ],
)
def test_every_operation_says_it_is_a_stub(grind, requests_mock, args, what):
    result = grind(*args)
    assert result.exit_code == 1
    assert (
        f"The 'github' provider (source 'oss') cannot do {what} yet: it is a stub."
        in result.output
    )
    assert requests_mock.call_count == 0
